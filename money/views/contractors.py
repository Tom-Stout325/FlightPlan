# money/views/contractors.py

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django import forms
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_GET


from money.forms.contractors.contractors import ContractorForm, ContractorW9UploadForm
from money.models import Contractor, Transaction, ContractorW9Submission

from money.utils.utils_token import parse_contractor_w9_token







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

        ctx.update(
            {
                "selected_year": year,
                "year_choices": year_choices,
                "transactions": tx_qs,
                "transaction_total": total,
                "current_page": "contractors",
                "has_w9_submission": has_w9_submission,
            }
        )
        return ctx


class ContractorDeleteView(LoginRequiredMixin, UserScopedQuerysetMixin, DeleteView):
    model = Contractor
    template_name = "money/contractors/contractor_confirm_delete.html"
    success_url = reverse_lazy("money:contractor_list")








# ----------------------------
# Signing / token utilities
# ----------------------------
signer = TimestampSigner(salt="money.contractor_w9")


def _get_contractor_from_token(
    token: str,
    *,
    max_age_seconds: int = 60 * 60 * 24 * 7,  # 7 days
) -> Contractor:
    """
    Token should be a signed contractor PK (string).
    Example token contents: "123" signed with TimestampSigner.
    """
    try:
        raw = signer.unsign(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise Http404("This W-9 link has expired.") from e
    except BadSignature as e:
        raise Http404("Invalid W-9 link.") from e

    return get_object_or_404(Contractor, pk=raw)


# ----------------------------
# Form
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
            "Single-member LLCs (disregarded entities) should NOT choose C, S, or P—"
            "instead, select Individual / Sole Proprietor above."
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

        sig_name = (cleaned.get("signature_name") or "").strip()
        if not sig_name:
            self.add_error("signature_name", "Please type your full name.")

        if cleaned.get("tax_classification") == "llc" and not cleaned.get("llc_tax_class"):
            self.add_error("llc_tax_class", "Select the LLC tax classification (C/S/P).")

        if cleaned.get("tax_classification") == "other" and not cleaned.get("other_tax_class"):
            self.add_error("other_tax_class", "Describe the tax classification.")

        return cleaned


# ----------------------------
# View
# ----------------------------
def contractor_w9(request: HttpRequest, token: str) -> HttpResponse:
    contractor = _get_contractor_from_token(token)
    already_submitted = ContractorW9Submission.objects.filter(contractor=contractor).exists()

    if already_submitted and request.method != "POST":
        ctx = {
            "contractor": contractor,
            "form": ContractorW9Form(),  
            "submitted": True,
            "already_submitted": True,
            "irs_w9_pdf_url": "https://www.irs.gov/pub/irs-pdf/fw9.pdf",
        }
        return render(request, "money/contractors/contractor_w9.html", ctx)

    if request.method == "POST":
        if already_submitted:
            return redirect(reverse("money:contractor_w9", kwargs={"token": token}) + "?submitted=1")

        form = ContractorW9Form(request.POST)
        if form.is_valid():
            _save_w9_submission(contractor, form.cleaned_data, request)
            return redirect(reverse("money:contractor_w9", kwargs={"token": token}) + "?submitted=1")
    else:
        form = ContractorW9Form()

    ctx = {
        "contractor": contractor,
        "form": form,
        "submitted": request.GET.get("submitted") == "1",
        "already_submitted": already_submitted,
        "irs_w9_pdf_url": "https://www.irs.gov/pub/irs-pdf/fw9.pdf",
    }
    return render(request, "money/contractors/contractor_w9.html", ctx)


# ----------------------------
# Persistence
# ----------------------------

def _save_w9_submission(contractor: Contractor, data: dict, request: HttpRequest) -> ContractorW9Submission:
    ip = request.META.get("REMOTE_ADDR") or None
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:2000]

    business_name   = data.get("business_name") or None
    llc_tax_class   = data.get("llc_tax_class") or None
    other_tax_class = data.get("other_tax_class") or None
    signature_data  = data.get("signature_data") or None


    tin = (data.get("tin") or "").strip().replace("-", "").replace(" ", "")
    tin_last4 = tin[-4:] if len(tin) >= 4 else ""

    submission = ContractorW9Submission.objects.create(
        user=contractor.user,
        contractor=contractor,

        full_name=data["full_name"],
        business_name=business_name,

        tax_classification=data["tax_classification"],
        llc_tax_class=llc_tax_class,
        other_tax_class=other_tax_class,

        address_line1=data["address_line1"],
        address_line2=data["address_line2"],

        tin_type=data["tin_type"],
        tin=tin,

        signature_name=data["signature_name"],
        signature_data=signature_data,
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
        {
            "contractor": contractor,
            "submission": submission,
            "show_tin": show_tin,
        },
    )







@require_http_methods(["GET", "POST"])
def contractor_w9(request, token: str):
    contractor_id = parse_contractor_w9_token(token)
    contractor = get_object_or_404(Contractor, pk=contractor_id, is_active=True)

    # Upload handler
    form = ContractorW9UploadForm(request.POST or None, request.FILES or None, instance=contractor)

    if request.method == "POST":
        if form.is_valid():
            form.save()

            # Update status metadata
            contractor.w9_status = Contractor.W9_RECEIVED
            contractor.w9_received_date = timezone.localdate()
            contractor.save(update_fields=["w9_status", "w9_received_date"])

            return redirect("money:contractor_w9_thanks", token=token)

    ctx = {
        "contractor": contractor,
        "form": form,
        "irs_w9_pdf_url": IRS_W9_PDF_URL,
        # If you have a separate “fill form” route, link it here:
        # "w9_fill_url": reverse("money:contractor_w9_fill", kwargs={"token": token}),
        "token": token,
    }
    return render(request, "money/contractors/w9_portal.html", ctx)


# money/views_contractors_w9.py




@require_GET
def contractor_w9_thanks(request, token: str):
    contractor_id = parse_contractor_w9_token(token)
    contractor = get_object_or_404(Contractor, pk=contractor_id, is_active=True)

    return render(
        request,
        "money/contractors/w9_thanks.html",
        {"contractor": contractor},
    )
