# money/views/contractors.py
from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Q, Sum
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from money.forms.contractors.contractors import ContractorForm, ContractorW9UploadForm  
from money.models import Contractor, ContractorW9Submission, Transaction, Contractor1099

from ..emails import W9EmailContext, send_w9_request_email



import logging
logger = logging.getLogger(__name__)


IRS_W9_PDF_URL = "https://www.irs.gov/pub/irs-pdf/fw9.pdf"


class UserScopedQuerysetMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)


class ContractorListView(LoginRequiredMixin, UserScopedQuerysetMixin, ListView):
    model = Contractor
    template_name = "money/contractors/contractor_list.html"
    context_object_name = "contractors"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().filter(is_active=True)

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(business_name__icontains=q)
                | Q(email__icontains=q)
                | Q(contractor_number__icontains=q)
            )

        return qs.order_by("last_name", "first_name", "id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["current_page"] = "contractors"
        return ctx


class ContractorCreateView(LoginRequiredMixin, CreateView):
    model = Contractor
    form_class = ContractorForm
    template_name = "money/contractors/contractor_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.user = self.request.user
        return form

    def get_success_url(self):
        return reverse_lazy("money:contractor_detail", kwargs={"pk": self.object.pk})


class ContractorUpdateView(LoginRequiredMixin, UserScopedQuerysetMixin, UpdateView):
    model = Contractor
    form_class = ContractorForm
    template_name = "money/contractors/contractor_form.html"

    def get_success_url(self):
        return reverse_lazy("money:contractor_detail", kwargs={"pk": self.object.pk})


class ContractorDetailView(LoginRequiredMixin, UserScopedQuerysetMixin, DetailView):
    model = Contractor
    template_name = "money/contractors/contractor_detail.html"
    context_object_name = "contractor"

    def _selected_year(self) -> int:
        y = self.request.GET.get("year")
        try:
            return int(y) if y else timezone.localdate().year
        except (TypeError, ValueError):
            return timezone.localdate().year

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        contractor = self.object
        year = self._selected_year()

        has_w9_submission = ContractorW9Submission.objects.filter(
            user=self.request.user,
            contractor=contractor,
        ).exists()

        tx_qs = (
            Transaction.objects
            .filter(user=self.request.user, contractor=contractor, date__year=year)
            .select_related("category", "sub_cat", "event", "team")
            .order_by("-date", "-id")
        )

        total = tx_qs.aggregate(total=Sum("amount"))["total"] or 0

        years = (
            Transaction.objects
            .filter(user=self.request.user, contractor=contractor)
            .dates("date", "year")
        )
        year_choices = sorted({d.year for d in years} | {timezone.localdate().year}, reverse=True)
        
        stored_1099 = (
            Contractor1099.objects
            .filter(user=self.request.user, contractor=contractor, tax_year=year)
            .only("id", "tax_year", "copy_b_pdf", "copy_1_pdf", "generated_at", "emailed_at", "emailed_to", "email_count")
            .first()
        )

        has_1099_copy_b = bool(stored_1099 and stored_1099.copy_b_pdf)
        has_1099_copy_1 = bool(stored_1099 and stored_1099.copy_1_pdf)


        ctx.update(
            {
                "selected_year": year,
                "year_choices": year_choices,
                "transactions": tx_qs,
                "transaction_total": total,
                "current_page": "contractors",
                "has_w9_submission": has_w9_submission,

                # 1099 storage/audit
                "stored_1099": stored_1099,
                "has_1099_copy_b": has_1099_copy_b,
                "has_1099_copy_1": has_1099_copy_1,
            }
        )
        return ctx


class ContractorDeleteView(LoginRequiredMixin, UserScopedQuerysetMixin, DeleteView):
    model = Contractor
    template_name = "money/contractors/contractor_confirm_delete.html"
    success_url = reverse_lazy("money:contractor_list")


# ----------------------------
# Secure W-9 token utilities
# ----------------------------
_W9_SIGNER = TimestampSigner(salt="money.contractor_w9")


def make_contractor_w9_token(contractor_pk: int) -> str:
    return _W9_SIGNER.sign(str(contractor_pk))


def contractor_pk_from_w9_token(token: str, *, max_age_seconds: int = 60 * 60 * 24 * 7) -> int:
    try:
        raw = _W9_SIGNER.unsign(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise Http404("This W-9 link has expired.") from e
    except BadSignature as e:
        raise Http404("Invalid W-9 link.") from e
    try:
        return int(raw)
    except (TypeError, ValueError) as e:
        raise Http404("Invalid W-9 link.") from e


def get_contractor_from_w9_token(token: str) -> Contractor:
    pk = contractor_pk_from_w9_token(token)
    return get_object_or_404(Contractor, pk=pk, is_active=True)


# ----------------------------
# W-9 “fill online” form
# ----------------------------
class ContractorW9Form(forms.Form):
    full_name = forms.CharField(label="Name (as shown on your income tax return)", max_length=200)
    business_name = forms.CharField(
        label="Business name / disregarded entity name (if different)",
        max_length=200,
        required=False,
    )

    TAX_CLASS_CHOICES = [
        ("individual", "Individual / Sole Proprietor"),
        ("c_corp", "C Corporation"),
        ("s_corp", "S Corporation"),
        ("partnership", "Partnership"),
        ("trust_estate", "Trust / Estate"),
        ("llc", "LLC"),
        ("other", "Other"),
    ]
    tax_classification = forms.ChoiceField(choices=TAX_CLASS_CHOICES, widget=forms.RadioSelect)

    LLC_TAX_CHOICES = [
        ("", "— Select LLC tax status —"),
        ("c", "C — C Corporation"),
        ("s", "S — S Corporation"),
        ("p", "P — Partnership"),
    ]
    llc_tax_class = forms.ChoiceField(
        label="How is your LLC taxed?",
        required=False,
        choices=LLC_TAX_CHOICES,
        help_text=(
            "Only complete this if you selected LLC above. "
            "Single-member LLCs (disregarded entities) should select Individual / Sole Proprietor."
        ),
    )

    other_tax_class = forms.CharField(label="If Other, describe", max_length=100, required=False)

    address_line1 = forms.CharField(label="Address (number, street, apt/suite)", max_length=200)
    address_line2 = forms.CharField(label="City, state, ZIP", max_length=200)

    TIN_TYPE = [("ssn", "SSN"), ("ein", "EIN")]
    tin_type = forms.ChoiceField(label="Taxpayer ID type", choices=TIN_TYPE, widget=forms.RadioSelect)
    tin = forms.CharField(
        label="Taxpayer Identification Number",
        max_length=20,
        help_text="Digits only is best. Do not include spaces or dashes.",
    )

    attestation = forms.BooleanField(
        required=True,
        label="I certify under penalties of perjury that the information provided is true, correct, and complete.",
    )
    signature_name = forms.CharField(label="Type your full name (signature)", max_length=200)
    signature_data = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
        help_text="Base64 PNG from the signature pad canvas.",
    )

    def clean(self):
        cleaned = super().clean()

        tin = (cleaned.get("tin") or "").strip().replace("-", "").replace(" ", "")
        cleaned["tin"] = tin

        if cleaned.get("tax_classification") == "llc" and not cleaned.get("llc_tax_class"):
            self.add_error("llc_tax_class", "Select the LLC tax classification (C/S/P).")

        if cleaned.get("tax_classification") == "other" and not cleaned.get("other_tax_class"):
            self.add_error("other_tax_class", "Describe the tax classification.")

        sig_name = (cleaned.get("signature_name") or "").strip()
        if not sig_name:
            self.add_error("signature_name", "Please type your full name.")

        return cleaned


def _save_w9_submission(contractor: Contractor, data: dict, request: HttpRequest) -> ContractorW9Submission:
    ip = request.META.get("REMOTE_ADDR") or None
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:2000]

    tin = (data.get("tin") or "").strip().replace("-", "").replace(" ", "")
    tin_last4 = tin[-4:] if len(tin) >= 4 else ""

    submission = ContractorW9Submission.objects.create(
        user=contractor.user,
        contractor=contractor,

        full_name=data["full_name"],
        business_name=(data.get("business_name") or None),

        tax_classification=data["tax_classification"],
        llc_tax_class=(data.get("llc_tax_class") or None),
        other_tax_class=(data.get("other_tax_class") or None),

        address_line1=data["address_line1"],
        address_line2=data["address_line2"],

        tin_type=data["tin_type"],
        tin=tin,

        signature_name=data["signature_name"],
        signature_data=(data.get("signature_data") or None),
        attested=True,

        submitted_ip=ip,
        submitted_ua=ua,
    )

    contractor.tin_type = data["tin_type"]
    contractor.tin_last4 = tin_last4
    contractor.w9_status = Contractor.W9_RECEIVED
    contractor.w9_received_date = timezone.localdate()
    contractor.save(update_fields=["tin_type", "tin_last4", "w9_status", "w9_received_date"])
    
    return submission


@require_http_methods(["GET", "POST"])
def contractor_w9_fill(request: HttpRequest, token: str) -> HttpResponse:
    contractor = get_contractor_from_w9_token(token)
    already_submitted = ContractorW9Submission.objects.filter(contractor=contractor).exists()

    if already_submitted and request.method != "POST":
        return render(
            request,
            "money/contractors/contractor_w9.html",
            {
                "contractor": contractor,
                "form": ContractorW9Form(),
                "submitted": True,
                "already_submitted": True,
                "irs_w9_pdf_url": IRS_W9_PDF_URL,
            },
        )

    if request.method == "POST":
        if already_submitted:
            return redirect(reverse("money:contractor_w9_fill", kwargs={"token": token}) + "?submitted=1")

        form = ContractorW9Form(request.POST)
        if form.is_valid():
            _save_w9_submission(contractor, form.cleaned_data, request)
            return redirect(reverse("money:contractor_w9_fill", kwargs={"token": token}) + "?submitted=1")
    else:
        form = ContractorW9Form()

    return render(
        request,
        "money/contractors/contractor_w9.html",
        {
            "contractor": contractor,
            "form": form,
            "submitted": request.GET.get("submitted") == "1",
            "already_submitted": already_submitted,
            "irs_w9_pdf_url": IRS_W9_PDF_URL,
        },
    )


@require_GET
def contractor_w9_thanks(request: HttpRequest, token: str) -> HttpResponse:
    contractor = get_contractor_from_w9_token(token)
    return render(request, "money/contractors/w9_thanks.html", {"contractor": contractor})


@login_required
def contractor_w9_admin(request: HttpRequest, pk: int) -> HttpResponse:
    contractor = get_object_or_404(Contractor, pk=pk, user=request.user)

    submission = (
        ContractorW9Submission.objects
        .filter(user=request.user, contractor=contractor)
        .order_by("-submitted_at", "-id")
        .first()
    )
    show_tin = request.GET.get("show_tin") == "1"

    return render(
        request,
        "money/contractors/contractor_w9_admin.html",
        {"contractor": contractor, "submission": submission, "show_tin": show_tin},
    )


logger = logging.getLogger(__name__)


@login_required
@require_POST
def contractor_send_w9_email(request: HttpRequest, pk: int) -> HttpResponse:
    contractor = get_object_or_404(Contractor, pk=pk, user=request.user)

    if not contractor.email:
        messages.error(request, "This contractor has no email address on file.")
        return redirect("money:contractor_detail", pk=contractor.pk)

    token = make_contractor_w9_token(contractor.pk)

    fill_path = reverse("money:contractor_w9_fill", kwargs={"token": token})
    fill_link = request.build_absolute_uri(fill_path)

    upload_path = reverse("money:contractor_w9_upload", kwargs={"token": token})
    upload_link = request.build_absolute_uri(upload_path)

    business_name = getattr(settings, "BRAND_NAME", "Airborne Images")
    business_phone = getattr(settings, "BRAND_PHONE", "")
    support_email = getattr(settings, "BRAND_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", ""))

    contractor_name = f"{(contractor.first_name or '').strip()} {(contractor.last_name or '').strip()}".strip() or "there"

    ctx = W9EmailContext(
        contractor_name=contractor_name,
        w9_fill_link=fill_link,
        w9_upload_link=upload_link,
        support_email=support_email,
        business_name=business_name,
        business_phone=business_phone,
    )

    try:
        # Send exactly once
        send_w9_request_email(to_email=contractor.email, ctx=ctx)

        # Tracking: never downgrade RECEIVED/VERIFIED back to REQUESTED
        today = timezone.localdate()
        update_fields = ["w9_sent_date"]
        contractor.w9_sent_date = today

        if contractor.w9_status in (Contractor.W9_NOT_REQUESTED, Contractor.W9_REQUESTED):
            contractor.w9_status = Contractor.W9_REQUESTED
            update_fields.append("w9_status")

        contractor.save(update_fields=update_fields)

        messages.success(request, f"W-9 request email sent to {contractor.email}.")
        return redirect("money:contractor_detail", pk=contractor.pk)

    except Exception:
        logger.exception(
            "W-9 email send failed (contractor_id=%s to=%s host=%s user=%s)",
            contractor.pk,
            contractor.email,
            getattr(settings, "EMAIL_HOST", ""),
            getattr(settings, "EMAIL_HOST_USER", ""),
        )
        messages.error(request, "Email failed to send. Please try again or check email settings/logs.")

        # Temporary: re-raise in production ONLY while debugging so you see the traceback.
        # Remove after you capture the real SMTP error.
        raise







@require_http_methods(["GET", "POST"])
def contractor_w9_upload(request: HttpRequest, token: str) -> HttpResponse:
    """
    Public endpoint (no login): contractor uploads a completed W-9 PDF/image.
    Uses the same signed token as the online-fill endpoint.
    """
    contractor = get_contractor_from_w9_token(token)

    # If you already have a W-9 submission, you can show a friendly message.
    already_submitted = ContractorW9Submission.objects.filter(contractor=contractor).exists()

    form = ContractorW9UploadForm(request.POST or None, request.FILES or None, instance=contractor)

    if request.method == "POST":
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = contractor.user  # keep ownership consistent
            obj.w9_status = Contractor.W9_RECEIVED
            obj.w9_received_date = timezone.localdate()
            obj.save()

            messages.success(request, "W-9 uploaded successfully. Thank you!")
            return redirect("money:contractor_w9_thanks", token=token)

    return render(
        request,
        "money/contractors/contractor_w9_upload.html",
        {
            "contractor": contractor,
            "form": form,
            "already_submitted": already_submitted,
            "irs_w9_pdf_url": IRS_W9_PDF_URL,
        },
    )
