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
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from weasyprint import CSS, HTML

from ..forms.invoices.invoices import (
    InvoiceForm,
    InvoiceItemFormSet,
)
from ..models import *







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
        # client_profile is already injected by context processor; no need to add explicitly
        return ctx

    def form_valid(self, form):
        formset = self.get_formset(self.request.POST)

        if not formset.is_valid():
            messages.error(self.request, "There were errors with the invoice items.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                invoice = form.save(commit=False)

                # Ensure issue/due are filled (in case user cleared them)
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

                # Placeholder for future snapshot of “from” fields (once added to Invoice)
                # if profile:
                #     invoice.from_name = profile.name_for_display
                #     invoice.from_address = "\n".join(profile.full_address_lines())
                #     ...

                invoice.amount = 0  # will be recalculated after items save
                invoice.save()

                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False):
                        item = item_form.save(commit=False)
                        item.invoice = invoice
                        item.save()

                # Recalculate totals
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
        ctx['formset'] = self.get_formset(self.request.POST if self.request.method == 'POST' else None)
        ctx['invoice'] = self.object
        ctx['current_page'] = 'invoices'
        return ctx

    def form_valid(self, form):
        formset = self.get_formset(self.request.POST)

        if not formset.is_valid():
            messages.error(self.request, "There were errors in the invoice items.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                invoice = form.save(commit=False)

                # If someone clears dates on edit, reapply profile defaults
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

    # Transactions
    transactions = (
        Transaction.objects
        .filter(event=invoice.event, invoice_number=invoice.invoice_number)
        .select_related('sub_cat__category')
    )

    # Mileage rate
    try:
        r = MileageRate.objects.first()
        rate = Decimal(str(r.rate)) if r and r.rate is not None else Decimal("0.70")
    except Exception:
        rate = Decimal("0.70")

    # Mileage rows (filter by invoice_number; Miles has no Invoice FK)
    base_mileage = (
        Miles.objects
        .filter(invoice_number=invoice.invoice_number, user=request.user, mileage_type="Taxable")
        .select_related('client', 'event')
        .order_by('date')
    )

    # miles = total if present, else end - begin, else 0
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

    # Income/expense summaries
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
        template = get_template('money/invoices/invoice_pdf_export.html')
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
            "money/invoice/invoice_detail.html",
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
                "money/invoice/invoice_email.html",
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

    from collections import defaultdict
    tx_index = defaultdict(list)
    for t in year_txns:
        key = (t.event_id, t.invoice_number or "")
        tx_index[key].append(t)

    for inv in invoices:
        key = (inv.event_id, inv.invoice_number or "")

        txns = tx_index.get(key, [])

        total_income = Decimal("0")
        total_expenses = Decimal("0")
        deductible_expenses = Decimal("0")

        for t in txns:
            if t.trans_type == Transaction.INCOME:
                total_income += t.amount
            else:
                total_expenses += t.amount
                if getattr(t, "sub_cat", None) and getattr(t.sub_cat, "slug", "") == "meals":
                    deductible_expenses += getattr(t, "deductible_amount", Decimal("0"))
                elif getattr(t, "sub_cat", None) and getattr(t.sub_cat, "slug", "") == "fuel" and t.transport_type == "personal_vehicle":
                    pass
                else:
                    deductible_expenses += t.amount

        inv_miles_qs = base_mileage.filter(
            event=inv.event, invoice_number=inv.invoice_number
        )

        miles_expr = ExpressionWrapper(
            F("total"),
            output_field=Transaction._meta.get_field("amount") 
        )
        miles_total = inv_miles_qs.aggregate(
            _sum=Sum(
                Case(
                    When(total__isnull=False, then=F("total")),
                    default=F("end") - F("begin"),
                )
            )
        )["_sum"] or Decimal("0")

        mileage_dollars = (miles_total or Decimal("0")) * mileage_rate

        has_income = total_income > 0
        net_income = (total_income - total_expenses) if has_income else None
        taxable_income = (total_income - deductible_expenses - mileage_dollars) if has_income else None

        rows.append({
            "pk": inv.pk,
            "invoice_number": inv.invoice_number or "",
            "event": inv.event,
            "invoice_amount": inv.amount or Decimal("0"),
            "total_expenses": total_expenses,
            "net_income": net_income,
            "taxable_income": taxable_income,
        })

    def _sum(key):
        total = Decimal("0")
        for r in rows:
            val = r.get(key)
            if val is not None:
                total += val
        return total

    totals = {
        "invoice_amount": _sum("invoice_amount"),
        "total_expenses": _sum("total_expenses"),
        "net_income":     _sum("net_income"),
        "taxable_income": _sum("taxable_income"),
    }

    return render(
        request,
        "money/invoices/invoice_summary.html",
        {
            "rows": rows,
            "years": years,
            "selected_year": selected_year,
            "totals": totals,
        },
    )
