# money/views/invoices_v2.py

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction as db_tx
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView
from django.http import Http404, HttpRequest, HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.utils import timezone
from django.core.mail import EmailMessage

from money.forms.invoices.invoice_v2 import InvoiceItemV2FormSet, InvoiceV2Form
from money.models import InvoiceV2
from money.models import CompanyProfile, InvoiceV2, Transaction

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

    html = render_to_string(
        "money/invoices/invoice_v2_pdf.html",
        {
            "invoice": invoice,
            "items": invoice.items.select_related("sub_cat", "category").all(),
            "profile": _get_active_profile(),
        },
        request=request,
    )
    return HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()



# -----------------------------------------------------------------------------
# Queryset scoping mixin (prevents cross-user access)
# -----------------------------------------------------------------------------
class InvoiceV2QuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return (
            InvoiceV2.objects.filter(user=self.request.user)
            .select_related("client", "event", "service")
            .prefetch_related("items")
            .order_by("-date", "-pk")
        )


# -----------------------------------------------------------------------------
# List / Detail
# -----------------------------------------------------------------------------
class InvoiceV2ListView(InvoiceV2QuerysetMixin, ListView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_list.html"
    context_object_name = "invoices"
    paginate_by = 25


class InvoiceV2DetailView(InvoiceV2QuerysetMixin, DetailView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_detail.html"
    context_object_name = "invoice"


# -----------------------------------------------------------------------------
# Create / Update (FBVs for predictable formset handling)
# -----------------------------------------------------------------------------
@login_required
def invoice_v2_create(request):
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
def invoice_v2_update(request, pk: int):
    """
    Update InvoiceV2 + inline InvoiceItemV2 rows.
    """
    invoice = get_object_or_404(InvoiceV2, user=request.user, pk=pk)

    if request.method == "POST":
        form = InvoiceV2Form(request.POST, instance=invoice, user=request.user)
        form.instance.user = request.user  # ✅ safety / required for OwnedModelMixin

        items_formset = InvoiceItemV2FormSet(
            request.POST,
            instance=invoice,
            prefix="items",
            user=request.user,  # ✅ sets item.user before validation
        )

        if form.is_valid() and items_formset.is_valid():
            with db_tx.atomic():
                invoice = form.save()  # header saved first

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
        {
            "form": form,
            "items_formset": items_formset,
            "invoice": invoice,
        },
    )


# -----------------------------------------------------------------------------
# Delete
# -----------------------------------------------------------------------------
class InvoiceV2DeleteView(InvoiceV2QuerysetMixin, DeleteView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_confirm_delete.html"
    success_url = reverse_lazy("money:invoice_v2_list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Invoice deleted.")
        return super().delete(request, *args, **kwargs)



# -----------------------------------------------------------------------------
# Detail
# -----------------------------------------------------------------------------
class InvoiceV2DetailView(LoginRequiredMixin, DetailView):
    model = InvoiceV2
    template_name = "money/invoices/invoice_v2_detail.html"
    context_object_name = "invoice"

    def get_object(self, queryset=None):
        return _require_invoice_v2_owned_by_user(self.request, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice: InvoiceV2 = context["invoice"]

        tx_list = []
        if invoice.invoice_number:
            tx_list = (
                Transaction.objects.filter(
                    user=self.request.user,
                    invoice_number=invoice.invoice_number,
                )
                .select_related("category", "sub_cat", "event")
                .order_by("date", "pk")
            )

        context["items"] = invoice.items.select_related("sub_cat", "category").all()
        context["tx_list"] = tx_list
        context["profile"] = _get_active_profile()
        return context



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
        invoice.save()

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
