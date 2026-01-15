# money/views/invoices_v2.py
from __future__ import annotations

from django.conf import settings
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import EmailMessage
from django.db import transaction as db_tx
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DeleteView, DetailView, ListView
from django.db.models.functions import Coalesce
from django.apps import apps
from money.forms.invoices.invoice_v2 import InvoiceItemV2FormSet, InvoiceV2Form
from money.models import Client, CompanyProfile, InvoiceV2, Transaction

try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False




# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _require_invoice_v2_owned_by_user(request: HttpRequest, pk: int) -> InvoiceV2:
    return get_object_or_404(
        InvoiceV2.objects.select_related("client", "event", "service"),
        pk=pk,
        user=request.user,
    )


def _get_active_profile() -> CompanyProfile | None:
    try:
        return CompanyProfile.get_active()
    except Exception:
        return None


def _absolute_logo_url(request: HttpRequest, profile: CompanyProfile | None) -> str | None:
    if not profile:
        return None
    logo = getattr(profile, "logo", None)
    if not logo:
        return None
    try:
        return request.build_absolute_uri(logo.url)
    except Exception:
        return None


def _render_invoice_v2_pdf_bytes(request: HttpRequest, invoice: InvoiceV2) -> bytes:
    if not WEASYPRINT_AVAILABLE:
        raise RuntimeError("WeasyPrint is not available.")

    profile = _get_active_profile()
    brand_logo_url = _absolute_logo_url(request, profile)

    # optional: if you already have a phone formatter helper, use it here
    formatted_brand_phone = getattr(profile, "main_phone", "") if profile else ""

    html = render_to_string(
        "money/invoices/invoice_v2_pdf.html",
        {
            "invoice": invoice,
            "items": invoice.items.select_related("sub_cat", "category").all(),

            # ✅ match what the template expects
            "BRAND_PROFILE": profile,
            "BRAND_LOGO_URL": brand_logo_url,
            "formatted_brand_phone": formatted_brand_phone,
        },
        request=request,
    )

    return HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()


# -----------------------------------------------------------------------------
# List
# -----------------------------------------------------------------------------
class InvoiceV2ListView(LoginRequiredMixin, ListView):
    """
    We keep get_queryset() as a real QuerySet for proper pagination and efficiency.
    In get_context_data(), we convert only the current page into dict "rows"
    because your template expects row.detail_url / row.review_url / etc.
    """

    model = InvoiceV2
    template_name = "money/invoices/invoice_list.html"
    context_object_name = "invoices"  # we'll override with rows
    paginate_by = 25

    def get_queryset(self):
        qs = (
            InvoiceV2.objects.filter(user=self.request.user)
            .select_related("client", "event", "service")
            .order_by("-date", "-invoice_number", "-pk")
        )

        status = (self.request.GET.get("status") or "").strip()
        year = (self.request.GET.get("year") or "").strip()
        client_id = (self.request.GET.get("client") or "").strip()
        q = (self.request.GET.get("q") or "").strip()

        if status:
            qs = qs.filter(status=status)

        if year:
            try:
                qs = qs.filter(date__year=int(year))
            except ValueError:
                pass

        if client_id:
            try:
                qs = qs.filter(client_id=int(client_id))
            except ValueError:
                pass

        if q:
            qs = qs.filter(
                Q(invoice_number__icontains=q)
                | Q(event_name__icontains=q)
                | Q(location__icontains=q)
                | Q(client__business__icontains=q)
                | Q(client__first__icontains=q)
                | Q(client__last__icontains=q)
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        page_qs = ctx["object_list"]
        rows = []
        for inv in page_qs:
            rows.append(
                {
                    "pk": inv.pk,
                    "invoice_number": inv.invoice_number,
                    "client_name": str(inv.client) if inv.client else "—",
                    "location": inv.location or "",
                    "event_name": inv.event_name or (inv.event.title if inv.event else ""),
                    "issue_date": inv.date,
                    "due_date": inv.due,
                    "total_amount": inv.amount,
                    "status": inv.status or "",
                    "detail_url": reverse("money:invoice_v2_detail", kwargs={"pk": inv.pk}),
                    "pdf_url": reverse("money:invoice_v2_pdf", kwargs={"pk": inv.pk}),
                }
            )
        ctx["invoices"] = rows

        ctx["status_choices"] = InvoiceV2.STATUS_CHOICES

        years = (
            InvoiceV2.objects.filter(user=self.request.user)
            .values_list("date__year", flat=True)
            .distinct()
            .order_by("-date__year")
        )
        ctx["years"] = list(years) or [timezone.localdate().year]

        ctx["clients"] = Client.objects.filter(user=self.request.user).order_by("business", "last", "first")

        ctx["selected_status"] = (self.request.GET.get("status") or "").strip()
        ctx["selected_year"] = (self.request.GET.get("year") or "").strip()
        ctx["selected_client"] = (self.request.GET.get("client") or "").strip()

        return ctx


# -----------------------------------------------------------------------------
# Detail
# -----------------------------------------------------------------------------

MEALS_SLUG = "meals"
FUEL_SLUG = "fuel"
RENTAL_CAR = "rental_car"

ZERO_MILES = Decimal("0.0")
ZERO_MONEY = Decimal("0.00")

ONE_DP = DecimalField(max_digits=10, decimal_places=1)
TWO_DP = DecimalField(max_digits=20, decimal_places=2)


class InvoiceV2DetailView(LoginRequiredMixin, DetailView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_detail.html"
    context_object_name = "invoice"

    def get_object(self, queryset=None):
        return _require_invoice_v2_owned_by_user(self.request, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice: InvoiceV2 = context["invoice"]
        user = self.request.user

        # ---------------------------
        # Related transactions (ALL: income + expense)
        # ---------------------------
        tx_list = Transaction.objects.none()
        if invoice.invoice_number:
            tx_list = (
                Transaction.objects.filter(user=user, invoice_number=invoice.invoice_number)
                .select_related("category", "sub_cat", "sub_cat__category", "event")
                .order_by("date", "pk")
            )

        # ---------------------------
        # Mileage (Miles model)
        # ---------------------------
        MilesModel = apps.get_model("money", "Miles")
        MileageRateModel = apps.get_model("money", "MileageRate")

        mileage_entries = (
            MilesModel.objects.filter(user=user, invoice_v2=invoice)
            .select_related("client", "event", "vehicle")
            .order_by("date", "pk")
        )

        if not mileage_entries.exists() and invoice.invoice_number:
            mileage_entries = (
                MilesModel.objects.filter(user=user, invoice_number=invoice.invoice_number)
                .select_related("client", "event", "vehicle")
                .order_by("date", "pk")
            )

        inv_year = invoice.date.year if invoice.date else timezone.localdate().year

        rate_obj = (
            MileageRateModel.objects.filter(user=user, year=inv_year).first()
            or MileageRateModel.objects.filter(user__isnull=True, year=inv_year).first()
            or MileageRateModel.objects.filter(user=user).order_by("-year").first()
            or MileageRateModel.objects.filter(user__isnull=True).order_by("-year").first()
        )

        mileage_rate = getattr(rate_obj, "rate", None) or ZERO_MONEY

        mileage_entries = mileage_entries.annotate(
            miles=Coalesce(F("total"), Value(ZERO_MILES), output_field=ONE_DP),
            amount=ExpressionWrapper(
                Coalesce(F("total"), Value(ZERO_MILES), output_field=ONE_DP) * Value(mileage_rate),
                output_field=TWO_DP,
            ),
        )

        total_mileage_miles = mileage_entries.aggregate(total=Sum("miles")).get("total") or ZERO_MILES
        mileage_dollars = mileage_entries.aggregate(total=Sum("amount")).get("total") or ZERO_MONEY

        # ---------------------------
        # Transaction totals
        # ---------------------------
        def _sum_amount(qs):
            return qs.aggregate(total=Sum("amount")).get("total") or ZERO_MONEY

        income_qs = tx_list.filter(trans_type=Transaction.INCOME)
        expense_qs = tx_list.filter(trans_type=Transaction.EXPENSE)

        income_total = _sum_amount(income_qs)
        expense_total = _sum_amount(expense_qs)

        meals_total = ZERO_MONEY
        rental_fuel_total = ZERO_MONEY
        other_expenses_total = ZERO_MONEY

        for t in expense_qs:
            sub_slug = (getattr(getattr(t, "sub_cat", None), "slug", "") or "").strip().lower()

            if sub_slug == MEALS_SLUG:
                meals_total += t.amount
            elif sub_slug == FUEL_SLUG and (t.transport_type or "") == RENTAL_CAR:
                rental_fuel_total += t.amount
            else:
                other_expenses_total += t.amount

        net_income = income_total - expense_total

        deductible_meals = meals_total * Decimal("0.50")
        deductible_expenses = other_expenses_total + rental_fuel_total + deductible_meals
        taxable_income = income_total - deductible_expenses - mileage_dollars

        # ---------------------------
        # Context 
        # ---------------------------
        context["items"] = invoice.items.select_related("sub_cat", "category").all()
        context["tx_list"] = tx_list
        context["profile"] = _get_active_profile()

        context["has_transactions"] = tx_list.exists()

        context["total_expenses"] = expense_total
        context["net_income_effective"] = net_income

        context["deductible_expenses"] = deductible_expenses
        context["mileage_rate"] = mileage_rate
        context["total_mileage_miles"] = total_mileage_miles
        context["mileage_dollars"] = mileage_dollars
        context["taxable_income"] = taxable_income

        context["mileage_entries"] = mileage_entries

        return context

# -----------------------------------------------------------------------------
# Create / Update (FBVs for predictable formset handling)
# -----------------------------------------------------------------------------
@login_required
def invoice_v2_create(request: HttpRequest) -> HttpResponse:
    parent = InvoiceV2(user=request.user)

    if request.method == "POST":
        form = InvoiceV2Form(request.POST, instance=parent, user=request.user)
        form.instance.user = request.user

        items_formset = InvoiceItemV2FormSet(
            request.POST,
            instance=parent,
            prefix="items",
            user=request.user,
        )

        if form.is_valid() and items_formset.is_valid():
            with db_tx.atomic():
                invoice = form.save()
                items_formset.instance = invoice
                items_formset.save()
                invoice.update_amount(save=True)

            messages.success(request, "Invoice created.")
            return redirect("money:invoice_v2_detail", pk=invoice.pk)

    else:
        form = InvoiceV2Form(instance=parent, user=request.user)
        items_formset = InvoiceItemV2FormSet(
            instance=parent,
            prefix="items",
            user=request.user,
        )

    return render(
        request,
        "money/invoices/invoice_v2_form.html",
        {"form": form, "items_formset": items_formset, "invoice": None},
    )


@login_required
def invoice_v2_update(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(InvoiceV2, user=request.user, pk=pk)

    if request.method == "POST":
        form = InvoiceV2Form(request.POST, instance=invoice, user=request.user)
        form.instance.user = request.user

        items_formset = InvoiceItemV2FormSet(
            request.POST,
            instance=invoice,
            prefix="items",
            user=request.user,
        )

        if form.is_valid() and items_formset.is_valid():
            with db_tx.atomic():
                invoice = form.save()

                items = items_formset.save(commit=False)
                for item in items:
                    item.user = request.user
                    item.invoice = invoice
                    item.save()

                for item in items_formset.deleted_objects:
                    item.delete()

                invoice.update_amount(save=True)

            messages.success(request, "Invoice updated.")
            return redirect("money:invoice_v2_detail", pk=invoice.pk)

    else:
        form = InvoiceV2Form(instance=invoice, user=request.user)
        items_formset = InvoiceItemV2FormSet(
            instance=invoice,
            prefix="items",
            user=request.user,
        )

    return render(
        request,
        "money/invoices/invoice_v2_form.html",
        {"form": form, "items_formset": items_formset, "invoice": invoice},
    )


# -----------------------------------------------------------------------------
# Delete
# -----------------------------------------------------------------------------
class InvoiceV2DeleteView(LoginRequiredMixin, DeleteView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_confirm_delete.html"
    success_url = reverse_lazy("money:invoice_list")

    def get_queryset(self):
        return InvoiceV2.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Invoice deleted.")
        return super().delete(request, *args, **kwargs)


# -----------------------------------------------------------------------------
# Mark paid
# -----------------------------------------------------------------------------
class InvoiceV2MarkPaidView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        invoice = _require_invoice_v2_owned_by_user(request, pk)

        try:
            invoice.mark_as_paid(user=request.user, commit=True)
        except Exception as e:
            messages.error(request, f"Could not mark as paid: {e}")
            return redirect("money:invoice_v2_detail", pk=invoice.pk)

        messages.success(request, "Invoice marked as paid and income transaction recorded.")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)


# -----------------------------------------------------------------------------
# Issue
# -----------------------------------------------------------------------------
class InvoiceV2IssueView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        invoice = _require_invoice_v2_owned_by_user(request, pk)

        if invoice.issued_at:
            messages.info(request, "Invoice already issued.")
            return redirect("money:invoice_v2_detail", pk=invoice.pk)

        profile = _get_active_profile()
        logo_url = _absolute_logo_url(request, profile)

        try:
            invoice.snapshot_from_profile(profile, absolute_logo_url=logo_url, overwrite=False)
        except Exception:
            pass

        invoice.issued_at = timezone.now()
        invoice.save(update_fields=["issued_at"])

        messages.success(request, "Invoice issued.")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)


# -----------------------------------------------------------------------------
# PDF
# -----------------------------------------------------------------------------
@login_required
def invoice_v2_pdf_view(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = _require_invoice_v2_owned_by_user(request, pk)

    if not WEASYPRINT_AVAILABLE:
        messages.error(request, "PDF generation is not available (WeasyPrint missing).")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    try:
        pdf_bytes = _render_invoice_v2_pdf_bytes(request, invoice)
    except Exception as e:
        messages.error(request, f"PDF generation failed: {e}")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    filename = f"invoice_{invoice.invoice_number or invoice.pk}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


# -----------------------------------------------------------------------------
# Email
# -----------------------------------------------------------------------------
@login_required
def invoice_v2_send_email(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = _require_invoice_v2_owned_by_user(request, pk)

    to_email = getattr(invoice.client, "email", None)
    if not to_email:
        messages.error(request, "Client has no email address.")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    if not WEASYPRINT_AVAILABLE:
        messages.error(request, "Emailing requires PDF generation (WeasyPrint missing).")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    try:
        pdf_bytes = _render_invoice_v2_pdf_bytes(request, invoice)
    except Exception as e:
        messages.error(request, f"Could not generate invoice PDF: {e}")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    subject = f"Invoice {invoice.invoice_number or invoice.pk}"
    body = render_to_string(
        "money/invoices/email_invoice_v2.txt",
        {"invoice": invoice},
        request=request,
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    email.attach(
        filename=f"invoice_{invoice.invoice_number or invoice.pk}.pdf",
        content=pdf_bytes,
        mimetype="application/pdf",
    )

    try:
        email.send(fail_silently=False)
    except Exception as e:
        messages.error(request, f"Email failed: {e}")
        return redirect("money:invoice_v2_detail", pk=invoice.pk)

    invoice.sent_at = timezone.now()
    invoice.sent_to = to_email
    invoice.sent_by = request.user
    invoice.save(update_fields=["sent_at", "sent_to", "sent_by"])

    messages.success(request, f"Invoice emailed to {to_email}.")
    return redirect("money:invoice_v2_detail", pk=invoice.pk)


# -----------------------------------------------------------------------------
# Review
# -----------------------------------------------------------------------------
@login_required
def invoice_v2_review(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = _require_invoice_v2_owned_by_user(request, pk)

    tx_list = []
    if invoice.invoice_number:
        tx_list = (
            Transaction.objects.filter(
                user=request.user,
                invoice_number=invoice.invoice_number,
            )
            .select_related("category", "sub_cat", "event")
            .order_by("date", "pk")
        )

    return render(
        request,
        "money/invoices/invoice_v2_review.html",
        {
            "invoice": invoice,
            "items": invoice.items.select_related("sub_cat", "category").all(),
            "tx_list": tx_list,
            "profile": _get_active_profile(),
        },
    )


@login_required
def invoice_review_router(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(InvoiceV2, pk=pk, user=request.user)
    return redirect("money:invoice_v2_review", pk=invoice.pk)
