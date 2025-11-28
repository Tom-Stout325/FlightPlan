import csv
import logging

logger = logging.getLogger(__name__)
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import EmailMessage
from django.db import transaction
from django.views import View
from django.db.models import (
    Case,
    DecimalField,
    ExpressionWrapper,
    F,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse_lazy
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
import hashlib
from django.core.files.base import ContentFile

from weasyprint import CSS, HTML

from ..forms.invoices.invoices import (
    InvoiceForm,
    InvoiceItemFormSet,
    InvoiceV2Form,
    InvoiceItemV2FormSet,
)
from ..models import *

from ..models import Client, ClientProfile



def generate_invoice_v2_pdf_snapshot(invoice: InvoiceV2, request) -> bytes:
    """
    Render the InvoiceV2 PDF, store it on the invoice as pdf_snapshot,
    update pdf_url + pdf_sha256, and return the PDF bytes.
    Always generates a NEW snapshot based on the current template.
    """
    # 1) Render HTML
    html_string = render_to_string(
        "money/invoices/invoice_v2_pdf.html",
        {"invoice": invoice},
        request=request,  # ensures context processors (branding, etc.) run
    )

    # 2) HTML -> PDF bytes with WeasyPrint
    weasy_html = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    )
    pdf_bytes = weasy_html.write_pdf()

    # 3) Hash for integrity + filename
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    short_hash = sha256[:8]
    filename = f"invoice-{invoice.invoice_number or invoice.pk}-{short_hash}.pdf"

    # 4) Store file via default storage
    invoice.pdf_snapshot.save(filename, ContentFile(pdf_bytes), save=False)
    invoice.pdf_sha256 = sha256

    try:
        invoice.pdf_url = invoice.pdf_snapshot.url
    except Exception:
        invoice.pdf_url = ""

    invoice.pdf_snapshot_created_at = timezone.now()
    invoice.save(
        update_fields=[
            "pdf_snapshot",
            "pdf_sha256",
            "pdf_url",
            "pdf_snapshot_created_at",
        ]
    )

    return pdf_bytes



class InvoiceV2FormsetMixin:
    """
    Mixin to attach an InvoiceItemV2 inline formset to Create/Update views.
    """

    def get_items_formset(self, instance=None):
        if self.request.method == "POST":
            return InvoiceItemV2FormSet(self.request.POST, instance=instance)
        return InvoiceItemV2FormSet(instance=instance)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = getattr(self, "object", None)
        context.setdefault("items_formset", self.get_items_formset(instance=instance))
        return context


def _today_in_profile_tz():
    return date.today()


def _compute_due(issue_dt, client_profile: ClientProfile | None):
    net_days = 30
    if client_profile and isinstance(client_profile.default_net_days, int):
        net_days = max(0, client_profile.default_net_days)
    return issue_dt + timedelta(days=net_days)


class InvoiceCreateView(LoginRequiredMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'money/invoices/invoice_add.html'
    success_url = reverse_lazy('money:invoice_list')

    def get_formset(self, data=None):
        return InvoiceItemFormSet(data)

    def get_initial(self):
        initial = super().get_initial()
        profile = ClientProfile.get_active()
        issue_dt = _today_in_profile_tz()
        # Only set if the form doesn't already supply initial values
        initial.setdefault("date", issue_dt)
        initial.setdefault("due", _compute_due(issue_dt, profile))
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # formset
        if self.request.method == 'POST':
            ctx['formset'] = self.get_formset(self.request.POST)
        else:
            ctx['formset'] = self.get_formset()
        ctx['current_page'] = 'invoices'
        return ctx

    def form_valid(self, form):
        formset = self.get_formset(self.request.POST)

        if not formset.is_valid():
            messages.error(self.request, "There were errors with the invoice items.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                invoice = form.save(commit=False)
                profile = ClientProfile.get_active()
                if not getattr(invoice, "date", None):
                    invoice.date = _today_in_profile_tz()
                if not getattr(invoice, "due", None):
                    invoice.due = _compute_due(invoice.date, profile)

                # If your Invoice model has currency/locale fields, set them here:
                if hasattr(invoice, "currency") and profile:
                    invoice.currency = getattr(profile, "default_currency", "USD")
                if hasattr(invoice, "locale") and profile:
                    invoice.locale = getattr(profile, "default_locale", "en_US")

                invoice.amount = 0  
                invoice.save()

                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False):
                        item = item_form.save(commit=False)
                        item.invoice = invoice
                        item.save()
                invoice.update_amount()

                messages.success(self.request, "Invoice created successfully.")
                return redirect(self.success_url)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            messages.error(self.request, f"Error saving invoice: {e}")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))



class InvoiceUpdateView(LoginRequiredMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'money/invoices/invoice_update.html'
    success_url = reverse_lazy('money:invoice_list')

    def get_formset(self, data=None):
        return InvoiceItemFormSet(data, instance=self.object)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.get_formset(
            self.request.POST if self.request.method == 'POST' else None
        )
        ctx['invoice'] = self.object
        ctx['current_page'] = 'invoices'
        return ctx

    def form_invalid(self, form):
        """
        DEBUG: see exactly why the POST is not redirecting.
        """
        formset = self.get_formset(self.request.POST)

        print("==== InvoiceUpdateView.form_invalid ====")
        print("FORM VALID:", form.is_valid())
        print("FORM ERRORS:", form.errors)
        print("FORMSET VALID:", formset.is_valid())
        print("FORMSET NON-FORM ERRORS:", formset.non_form_errors())
        print("FORMSET PER-FORM ERRORS:", [f.errors for f in formset.forms])

        messages.error(self.request, "There were errors in the invoice or items.")
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def form_valid(self, form):
        formset = self.get_formset(self.request.POST)

        if not formset.is_valid():
            messages.error(self.request, "There were errors in the invoice items.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                invoice = form.save(commit=False)
                profile = ClientProfile.get_active()
                if not getattr(invoice, "date", None):
                    invoice.date = _today_in_profile_tz()
                if not getattr(invoice, "due", None) and getattr(invoice, "date", None):
                    invoice.due = _compute_due(invoice.date, profile)

                invoice.save()
                formset.save()
                invoice.update_amount()

                messages.success(self.request, "Invoice updated successfully.")
                return redirect(self.success_url)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            messages.error(self.request, "Error updating invoice. Please check the form.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))


class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = "money/invoices/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 20

    def get_ordering(self):
        sort = self.request.GET.get('sort', 'invoice_number')
        direction = self.request.GET.get('direction', 'desc')

        valid_sort_fields = [
            'invoice_number',  
            'client__business',
            'event__title',
            'service__service',
            'amount',
            'date',
            'due',
            'paid_date',
        ]

        if sort not in valid_sort_fields:
            sort = 'invoice_number'

        return f"-{sort}" if direction == 'desc' else sort

    def get_queryset(self):
        ordering = self.get_ordering()

        queryset = Invoice.objects.select_related(
            'client', 'event', 'service'
        ).prefetch_related('items').order_by(ordering)

        search_query = self.request.GET.get('search', '')
        if search_query:
            search_query = search_query[:100]
            if hasattr(Invoice, 'search_vector'):
                queryset = queryset.filter(search_vector=search_query)
            else:
                queryset = queryset.filter(transaction__icontains=search_query)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'search_query': self.request.GET.get('search', ''),
            'current_sort': self.request.GET.get('sort', 'invoice_number'), 
            'current_direction': self.request.GET.get('direction', 'desc'),
            'current_page': 'invoices',
        })
        return context



class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'money/invoices/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return Invoice.objects.select_related(
            'client', 'event', 'service'
        ).prefetch_related('items')

    @cached_property
    def logo_path(self):
        """Resolve the logo file path if available."""
        dirs = getattr(settings, 'STATICFILES_DIRS', [])
        for directory in dirs:
            potential_path = os.path.join(directory, 'images/logo2.png')
            if os.path.exists(potential_path):
                return f'file://{potential_path}'
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'logo_path': self.logo_path,
            'rendering_for_pdf': self.request.GET.get('pdf', '').lower() in ['1', 'true'],
            'current_page': 'invoices',
        })
        return context


class InvoiceDeleteView(LoginRequiredMixin, DeleteView):
    model = Invoice
    template_name = "money/invoices/invoice_confirm_delete.html"
    success_url = reverse_lazy('money:invoice_list')

    def delete(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                response = super().delete(request, *args, **kwargs)
                messages.success(self.request, "Invoice deleted successfully.")
                return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete invoice due to related records.")
            return redirect('money:invoice_list')
        except Exception as e:
            logger.error(f"Error deleting invoice for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting invoice.")
            return redirect('money:invoice_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'invoices'
        return context
    

@login_required
def invoice_review(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    transactions = Transaction.objects.filter(
        event=invoice.event,
        invoice_number=invoice.invoice_number
    ).select_related('sub_cat__category')

    # mileage rate
    try:
        r = MileageRate.objects.first()
        rate = Decimal(str(r.rate)) if r and r.rate is not None else Decimal("0.70")
    except Exception:
        rate = Decimal("0.70")

    base_mileage = Miles.objects.filter(
        invoice_number=invoice.invoice_number,
        user=request.user,
        mileage_type="Taxable",
    ).select_related('client', 'event')

    miles_expr = ExpressionWrapper(
        Coalesce(F('total'), F('end') - F('begin'), Value(0)),
        output_field=DecimalField(max_digits=12, decimal_places=1),
    )

    amount_expr = Case(
        When(
            mileage_type="Taxable",
            then=ExpressionWrapper(
                F('miles') * Value(rate),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        ),
        default=Value(0),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    mileage_entries = (
        base_mileage
        .annotate(miles=miles_expr)
        .annotate(amount=amount_expr)
        .order_by('date')
    )

    totals = mileage_entries.aggregate(
        total_mileage_miles=Sum('miles'),
        mileage_dollars=Sum('amount'),
    )
    total_mileage_miles = totals['total_mileage_miles'] or Decimal('0')
    mileage_dollars = totals['mileage_dollars'] or Decimal('0')
    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")
    deductible_expenses = Decimal("0.00")
    for t in transactions:
        if t.trans_type == 'Income':
            total_income += t.amount
        elif t.trans_type == 'Expense':
            total_expenses += t.amount
            if t.sub_cat and t.sub_cat.slug == 'meals':
                deductible_expenses += t.deductible_amount
            elif t.sub_cat and t.sub_cat.slug == 'fuel' and t.transport_type == "personal_vehicle":
                continue
            else:
                deductible_expenses += t.amount

    has_income_transaction = total_income > 0
    total_cost = total_expenses + mileage_dollars
    net_income = total_income - total_expenses if has_income_transaction else None
    taxable_income = total_income - deductible_expenses - mileage_dollars if has_income_transaction else None

    context = {
        'invoice': invoice,
        'transactions': transactions,
        'mileage_entries': mileage_entries,
        'mileage_rate': rate,
        'mileage_dollars': mileage_dollars,    
        'total_mileage_miles': total_mileage_miles, 
        'invoice_amount': invoice.amount,
        'total_expenses': total_expenses,
        'deductible_expenses': deductible_expenses,
        'total_income': total_income,
        'net_income': net_income,
        'taxable_income': taxable_income,
        'total_cost': total_cost,
        'has_income_transaction': has_income_transaction,
        'now': now(),
        'current_page': 'invoices',
    }
    return render(request, 'money/invoices/invoice_review.html', context)





@login_required
def invoice_review_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    transactions = (
        Transaction.objects
        .filter(event=invoice.event, invoice_number=invoice.invoice_number)
        .select_related('sub_cat__category')
    )
    try:
        r = MileageRate.objects.first()
        rate = Decimal(str(r.rate)) if r and r.rate is not None else Decimal("0.70")
    except Exception:
        rate = Decimal("0.70")

    base_mileage = (
        Miles.objects
        .filter(invoice_number=invoice.invoice_number, user=request.user, mileage_type="Taxable")
        .select_related('client', 'event')
        .order_by('date')
    )

    miles_expr = ExpressionWrapper(
        Coalesce(F('total'), F('end') - F('begin'), Value(0)),
        output_field=DecimalField(max_digits=12, decimal_places=1),
    )
    amount_expr = Case(
        When(
            mileage_type="Taxable",
            then=ExpressionWrapper(
                F('miles') * Value(rate),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        ),
        default=Value(0),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    mileage_entries = base_mileage.annotate(miles=miles_expr).annotate(amount=amount_expr)

    totals = mileage_entries.aggregate(
        total_mileage_miles=Sum('miles'),
        mileage_dollars=Sum('amount'),
    )
    total_mileage_miles = totals['total_mileage_miles'] or Decimal('0')
    mileage_dollars = totals['mileage_dollars'] or Decimal('0')
    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")
    deductible_expenses = Decimal("0.00")

    for t in transactions:
        if t.trans_type == 'Income':
            total_income += t.amount
        elif t.trans_type == 'Expense':
            total_expenses += t.amount
            if t.sub_cat and t.sub_cat.slug == 'meals':
                deductible_expenses += t.deductible_amount
            elif t.sub_cat and t.sub_cat.slug == 'fuel' and t.transport_type == "personal_vehicle":
                continue
            else:
                deductible_expenses += t.amount

    has_income_transaction = total_income > 0
    net_income = total_income - total_expenses if has_income_transaction else None
    taxable_income = (total_income - deductible_expenses - mileage_dollars) if has_income_transaction else None
    total_cost = total_expenses + mileage_dollars

    context = {
        'invoice': invoice,
        'transactions': transactions,
        'mileage_entries': mileage_entries,
        'mileage_rate': rate,
        'total_mileage_miles': total_mileage_miles,
        'mileage_dollars': mileage_dollars,
        'invoice_amount': invoice.amount,
        'total_expenses': total_expenses,
        'deductible_expenses': deductible_expenses,
        'total_income': total_income,
        'net_income': net_income,
        'taxable_income': taxable_income,
        'total_cost': total_cost,
        'has_income_transaction': has_income_transaction,
        'now': now(),
    }

    html_string = render_to_string('money/invoices/invoice_review_pdf.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf = html.write_pdf(stylesheets=[CSS(string='@page { size: A4; margin: 1in; }')])

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=invoice_{invoice.invoice_number}.pdf'
    return response
    return response



@login_required
def unpaid_invoices(request):
    invoices = Invoice.objects.filter(paid__iexact="No").select_related('client').order_by('due_date')
    context = {'invoices': invoices, 'current_page': 'invoices'}
    return render(request, 'money/invoices/unpaid_invoices.html', context)




@login_required
def export_invoices_csv(request):
    invoices = Invoice.objects.select_related('client', 'event', 'service', 'invoice_number')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="invoices.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Invoice #',
        'Client',
        'Event',
        'Location',
        'Event',
        'Service',
        'Amount',
        'Date',
        'Due Date',
        'Paid Date',
        'Status',
    ])

    for inv in invoices:
        writer.writerow([
            inv.invoice_number.invoice_number if inv.invoice_number else '',
            str(inv.client) if inv.client else '',
            inv.event if inv.event else '',
            inv.location if inv.location else '',
            str(inv.event) if inv.event else '',
            str(inv.service) if inv.service else '',
            f"{inv.amount:.2f}",
            inv.date.strftime('%Y-%m-%d') if inv.date else '',
            inv.due.strftime('%Y-%m-%d') if inv.due else '',
            inv.paid_date.strftime('%Y-%m-%d') if inv.paid_date else '',
            inv.status,
        ])

    return response




@login_required
def export_invoices_pdf(request):
    invoice_view = InvoiceListView()
    invoice_view.request = request
    invoices = invoice_view.get_queryset()[:1000]

    if not invoices.exists():
        messages.error(request, "No invoices to export.")
        return redirect('money:invoice_list')

    try:
        template = get_template('money/invoice_pdf_export.html')
        html_string = template.render({'invoices': invoices, 'current_page': 'invoices'})
        with tempfile.NamedTemporaryFile(delete=True) as output:
            HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(output.name)
            output.seek(0)
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="invoices.pdf"'
            response.write(output.read())
            return response
    except Exception as e:
        logger.error(f"Error generating PDF for user {request.user.id}: {e}")
        messages.error(request, "Error generating PDF.")
        return redirect('money:invoice_list')
    


@login_required
def invoice_summary(request: HttpRequest) -> HttpResponse:
    all_years_qs = (
        Invoice.objects
        .exclude(date__isnull=True)
        .values_list("date__year", flat=True)
        .distinct()
        .order_by("-date__year")
    )
    years = list(all_years_qs) or [now().year]
    selected_year = request.GET.get("year")
    try:
        selected_year = int(selected_year) if selected_year else years[0]
    except (TypeError, ValueError):
        selected_year = years[0]

    invoices = (
        Invoice.objects
        .select_related("event", "client", "service")
        .filter(date__year=selected_year)
        .order_by("date", "invoice_number")
    )

    try:
        r = MileageRate.objects.first()
        mileage_rate = Decimal(str(r.rate)) if r and r.rate is not None else Decimal("0.70")
    except Exception:
        mileage_rate = Decimal("0.70")

    rows = []

    year_txns = (
        Transaction.objects
        .filter(date__year=selected_year)
        .select_related("sub_cat__category", "event")
    )

    base_mileage = (
        Miles.objects
        .filter(date__year=selected_year, user=request.user, mileage_type="Taxable")
    )



@require_POST
def send_invoice_email(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)

    # Safe access helpers (handles minor model field name variations)
    def get_first_name(client):
        return getattr(client, "first", None) or getattr(client, "first_name", "") or client.__class__.__name__

    def get_invoice_number(inv):
        return getattr(inv, "invoice_number", None) or getattr(inv, "invoice_number", None) or str(inv.pk)

    try:
        # Render invoice HTML (the same template you already use) and build PDF
        html_string = render_to_string(
            "money/invoice_detail.html",
            {"invoice": invoice, "current_page": "invoices"}
        )
        # base_url should be the site root so /static/... resolves in WeasyPrint
        pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

        inv_no = get_invoice_number(invoice)
        client_first = get_first_name(invoice.client)

        # Subject & body using brand settings
        subject = f"Invoice #{inv_no} from {settings.BRAND_NAME}"


        # Option A: inline body (simple + reliable)
        body = render_to_string(
                "money/invoice_email.html",
                {"client_first": client_first, "invoice": invoice}
            )


        # Fallback recipient logic
        recipient_email = invoice.client.email if getattr(invoice.client, "email", None) else getattr(settings, "DEFAULT_FROM_EMAIL", None)
        if not recipient_email:
            raise ValueError("No valid recipient email found (client email missing and DEFAULT_FROM_EMAIL not set).")

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.BRAND_EMAIL or settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
            bcc=list(settings.BRAND_BCC) if isinstance(settings.BRAND_BCC, (list, tuple)) else [settings.BRAND_BCC],
            reply_to=[settings.BRAND_EMAIL or settings.DEFAULT_FROM_EMAIL],
        )
        email.content_subtype = "html"
        email.attach(f"Invoice_{inv_no}.pdf", pdf_file, "application/pdf")
        email.send()

        return JsonResponse({"status": "success", "message": "Invoice emailed successfully!"})

    except Exception as e:
        logger.error(f"Error sending email for invoice {invoice_id} by user {getattr(request.user, 'id', 'anon')}: {e}")
        return JsonResponse({"status": "error", "message": "Failed to send email"}, status=500)






#------------------------------------------------------------------------------------------------------  N E W   I N V O I C E S

class InvoiceV2CreateView(LoginRequiredMixin, CreateView):
    model = InvoiceV2
    form_class = InvoiceV2Form
    template_name = "money/invoices/invoice_v2_form.html"
    context_object_name = "invoice"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["items_formset"] = InvoiceItemV2FormSet(self.request.POST)
        else:
            context["items_formset"] = InvoiceItemV2FormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        items_formset = context["items_formset"]

        if not items_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        # Save invoice first
        self.object = form.save()

        # Attach items to this invoice and save
        items_formset.instance = self.object
        items_formset.save()

        # Recalculate amount
        self.object.update_amount()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("money:invoice_v2_detail", kwargs={"pk": self.object.pk})


class InvoiceV2UpdateView(LoginRequiredMixin, UpdateView):
    model = InvoiceV2
    form_class = InvoiceV2Form
    template_name = "money/invoices/invoice_v2_form.html"
    context_object_name = "invoice"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["items_formset"] = InvoiceItemV2FormSet(
                self.request.POST,
                instance=self.object,
            )
        else:
            # 👈 This is what makes existing line items appear on edit
            context["items_formset"] = InvoiceItemV2FormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        items_formset = context["items_formset"]

        if not items_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        self.object = form.save()

        items_formset.instance = self.object
        items_formset.save()

        self.object.update_amount()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("money:invoice_v2_detail", kwargs={"pk": self.object.pk})

class InvoiceV2ListView(LoginRequiredMixin, ListView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_list.html"
    context_object_name = "invoices"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            InvoiceV2.objects
            .select_related("client", "event", "service")
            .prefetch_related("items__sub_cat", "items__category")
            .order_by("-date", "-invoice_number")
        )

        status = self.request.GET.get("status")
        year = self.request.GET.get("year")
        client_id = self.request.GET.get("client")

        if status:
            qs = qs.filter(status=status)

        if year:
            qs = qs.filter(date__year=year)

        if client_id:
            qs = qs.filter(client_id=client_id)

        return qs

    def get_context_data(self, **kwargs):
        from django.db.models import Min, Max
        context = super().get_context_data(**kwargs)

        # For simple filters
        years = (
            InvoiceV2.objects
            .order_by()
            .values_list("date__year", flat=True)
            .distinct()
        )
        context["years"] = sorted(set(y for y in years if y))

        context["status_choices"] = InvoiceV2.STATUS_CHOICES
        context["selected_status"] = self.request.GET.get("status") or ""
        context["selected_year"] = self.request.GET.get("year") or ""
        context["selected_client"] = self.request.GET.get("client") or ""

        # You can swap this later to only show active clients
        context["clients"] = Client.objects.all().order_by("business")

        return context

class InvoiceV2DetailView(LoginRequiredMixin, DetailView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return (
            InvoiceV2.objects
            .select_related("client", "event", "service")
            .prefetch_related("items__sub_cat", "items__category")
        )

    def get_context_data(self, **kwargs):
        from decimal import Decimal  # ok to keep local or use module-level

        context = super().get_context_data(**kwargs)
        invoice: InvoiceV2 = self.object

        # ---------- Transactions / Net Income ----------
        # All transactions linked to this invoice number
        tx_qs = Transaction.objects.filter(invoice_number=invoice.invoice_number)
        has_transactions = tx_qs.exists()

        # Base net income from model helper (may be 0 if no transactions)
        net_income = invoice.net_income or Decimal("0.00")

        # If there are no transactions, treat Net Income as the invoice amount
        if not has_transactions:
            net_income_effective = invoice.amount or Decimal("0.00")
        else:
            net_income_effective = net_income

        # ---------- Mileage dollars (Taxable only) ----------
        try:
            rate_obj = MileageRate.objects.first()
            mileage_rate = (
                Decimal(str(rate_obj.rate))
                if rate_obj and rate_obj.rate is not None
                else Decimal("0.70")
            )
        except Exception:
            mileage_rate = Decimal("0.70")

        base_mileage = Miles.objects.filter(
            invoice_v2=invoice,
            user=self.request.user,
            mileage_type="Taxable",
        )

        miles_expr = ExpressionWrapper(
            Coalesce(F("total"), F("end") - F("begin"), Value(0)),
            output_field=DecimalField(max_digits=12, decimal_places=1),
        )

        amount_expr = ExpressionWrapper(
            F("miles") * Value(mileage_rate),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

        mileage_qs = (
            base_mileage
            .annotate(miles=miles_expr)
            .annotate(amount=amount_expr)
        )

        totals = mileage_qs.aggregate(
            total_miles=Sum("miles"),
            mileage_dollars=Sum("amount"),
        )
        mileage_dollars = totals["mileage_dollars"] or Decimal("0.00")
        total_mileage_miles = totals["total_miles"] or Decimal("0.0")

        # ---------- Taxable income = Net income (effective) - mileage dollars ----------
        taxable_income = net_income_effective - mileage_dollars

        context.update(
            {
                "has_transactions": has_transactions,
                "net_income_effective": net_income_effective,
                "mileage_entries": mileage_qs,
                "mileage_rate": mileage_rate,
                "mileage_dollars": mileage_dollars,
                "total_mileage_miles": total_mileage_miles,
                "taxable_income": taxable_income,
            }
        )

        return context


class InvoiceV2MarkPaidView(LoginRequiredMixin, View):
    """
    POST-only view to mark an invoice as Paid and create an income Transaction
    based on the first invoice item’s SubCategory.
    """

    def post(self, request, pk, *args, **kwargs):
        invoice = get_object_or_404(
            InvoiceV2.objects.select_related("client", "event", "service"),
            pk=pk,
        )

        # Safety: don’t double-mark as paid
        if invoice.is_paid:
            messages.info(request, "This invoice is already marked as paid.")
            return redirect("money:invoice_v2_detail", pk=invoice.pk)

        try:
            invoice.mark_as_paid(user=request.user)
        except Exception as exc:
            messages.error(
                request,
                f"Unable to mark invoice as paid: {exc}",
            )
        else:
            messages.success(
                request,
                "Invoice marked as paid and income transaction created.",
            )

        return redirect("money:invoice_v2_detail", pk=invoice.pk)



class InvoiceV2IssueView(LoginRequiredMixin, View):
    """
    POST-only view to 'issue' an invoice:
    - snapshots business details from the active ClientProfile
    - sets issued_at
    - generates a permanent PDF snapshot
    """

    def post(self, request, pk, *args, **kwargs):
        invoice = get_object_or_404(InvoiceV2, pk=pk)

        # Already issued? Just bounce back.
        if invoice.is_locked:
            messages.info(request, "This invoice has already been issued.")
            return redirect("money:invoice_v2_detail", pk=invoice.pk)

        # Must have at least one line item
        if not invoice.items.exists():
            messages.error(request, "Add at least one line item before issuing this invoice.")
            return redirect("money:invoice_v2_edit", pk=invoice.pk)

        # Get the active client profile for branding/snapshot
        profile = ClientProfile.objects.filter(is_active=True).first()
        if not profile:
            messages.error(
                request,
                "No active client profile is configured. Set one in the admin before issuing invoices.",
            )
            return redirect("money:invoice_v2_detail", pk=invoice.pk)

        # Try to build an absolute logo URL if a logo exists
        absolute_logo_url = None
        logo = getattr(profile, "logo", None)
        if logo:
            try:
                absolute_logo_url = request.build_absolute_uri(logo.url)
            except Exception:
                absolute_logo_url = None

        # Snapshot "From" details from the active profile
        invoice.snapshot_from_profile(profile, absolute_logo_url=absolute_logo_url)

        # Mark as issued (locks the invoice via is_locked property)
        if not invoice.issued_at:
            invoice.issued_at = timezone.now()

        # If due is empty, compute from invoice.date + profile.default_net_days
        if not invoice.due and invoice.date:
            net_days = getattr(profile, "default_net_days", 30) or 30
            invoice.due = invoice.date + timedelta(days=int(net_days))

        invoice.save()

        # 🔐 Generate and store the permanent PDF snapshot
        generate_invoice_v2_pdf_snapshot(invoice, request)

        messages.success(request, "Invoice issued and PDF snapshot created.")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)





def invoice_pdf_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    context = {
        "invoice": invoice,
        # include anything else your detail template expects:
        # "line_items": invoice.items.all(),
        # "client": invoice.client,
    }

    html_string = render_to_string(
        "money/invoices/invoice_pdf.html",  # new template below
        context=context,
        request=request,
    )

    html = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/")  # resolves static files
    )

    pdf_bytes = html.write_pdf()

    filename = f"Invoice-{invoice.invoice_number or invoice.id}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response





 

@login_required
def invoice_v2_pdf_view(request, pk):
    invoice = get_object_or_404(InvoiceV2, pk=pk)

    # Prefer stored snapshot if exists
    if getattr(invoice, "has_pdf_snapshot", None) and invoice.has_pdf_snapshot:
        pdf_bytes = invoice.pdf_snapshot.read()
    else:
        # If somehow missing (e.g. old invoice before snapshots), generate now
        pdf_bytes = generate_invoice_v2_pdf_snapshot(invoice, request)

    filename = f"Invoice-{invoice.invoice_number or invoice.pk}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response




@login_required
def invoice_v2_send_email(request, pk):
    """
    Email InvoiceV2 to the client.

    - Requires the invoice to be issued (locked).
    - Uses the stored PDF snapshot if available.
    - If no snapshot exists, generates one with generate_invoice_v2_pdf_snapshot().
    - Records sent_at, sent_to, and sent_by on the invoice.
    """
    invoice = get_object_or_404(InvoiceV2, pk=pk)

    # Require issued/locked before emailing
    if not invoice.is_locked:
        messages.error(request, "You must issue this invoice before emailing it.")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    # Require client email
    to_email = getattr(invoice.client, "email", None)
    if not to_email:
        messages.error(request, "This client does not have an email address.")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    # Brand info from active ClientProfile
    brand_profile = ClientProfile.get_active()
    brand_name = brand_profile.name_for_display if brand_profile else "Invoice"

    # ---- PDF bytes: prefer stored snapshot, else generate now ----
    if getattr(invoice, "has_pdf_snapshot", None) and invoice.has_pdf_snapshot:
        # Read existing snapshot file
        pdf_filefield = invoice.pdf_snapshot
        pdf_bytes = pdf_filefield.read()
        filename = (
            os.path.basename(pdf_filefield.name)
            or f"Invoice-{invoice.invoice_number or invoice.pk}.pdf"
        )
    else:
        # Create a new snapshot and use its bytes
        pdf_bytes = generate_invoice_v2_pdf_snapshot(invoice, request)
        filename = f"Invoice-{invoice.invoice_number or invoice.pk}.pdf"

    # ---- Email subject/body ----
    subject = f"{brand_name} Invoice {invoice.invoice_number or invoice.pk}"
    body = render_to_string(
        "money/invoices/email_invoice_v2_body.txt",
        {
            "invoice": invoice,
            "brand_name": brand_name,
        },
    )

    from_email = (
        getattr(brand_profile, "invoice_reply_to_email", "")
        or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or to_email
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[to_email],
    )
    email.attach(filename, pdf_bytes, "application/pdf")
    email.send()

    # Record metadata
    invoice.sent_at = timezone.now()
    invoice.sent_to = to_email
    invoice.sent_by = request.user
    invoice.save(update_fields=["sent_at", "sent_to", "sent_by"])

    messages.success(request, f"Invoice emailed to {to_email}.")
    return redirect("money:invoice_v2_detail", pk=invoice.pk)

