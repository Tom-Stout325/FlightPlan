# money/views/contractor_1099.py
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.urls import reverse
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from money.constants.state_1099 import STATES_REQUIRE_BOX7_STATE_INCOME
from money.utils.pdf_1099nec import COPY_B_AND_1_LAYOUT, render_1099nec_copy_b_and_1

from money.models import (
            CompanyProfile, 
            Contractor, 
            ContractorW9Submission, 
            Transaction,
            Contractor1099,
)



# --------------------------------------------------------------------------------------
# Business rules / helpers
# --------------------------------------------------------------------------------------

def box7_state_income(*, company: CompanyProfile, contractor: Contractor, box1_total: Decimal) -> str:
    """
    Box 7 (State income) — only populated if:
      - company enables state 1099 reporting
      - contractor has a state
      - contractor.state is in STATES_REQUIRE_BOX7_STATE_INCOME
    """
    if not company.state_1099_reporting_enabled:
        return ""

    st = (contractor.state or "").strip().upper()
    if not st:
        return ""

    if st not in STATES_REQUIRE_BOX7_STATE_INCOME:
        return ""

    return f"{box1_total:,.2f}"


def _selected_year_or_404(tax_year: int) -> int:
    if tax_year < 2000 or tax_year > 2100:
        raise Http404("Invalid tax year.")
    return tax_year


def _active_company_profile_or_404() -> CompanyProfile:
    profile = CompanyProfile.objects.filter(is_active=True).first()
    if not profile:
        raise Http404("No active CompanyProfile found.")
    return profile


def _normalize_tin(raw: str) -> str:
    """Digits only (no dashes/spaces)."""
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def _payer_display_name(company: CompanyProfile) -> str:
    return (company.display_name or company.legal_name or "").strip() or "Business"


def _payer_tin_full(company: CompanyProfile) -> str:
    return _normalize_tin((company.tax_id_ein or "").strip())


def _payer_block_lines(company: CompanyProfile) -> str:
    """
    Multi-line payer block (name + address + phone).
    Matches the IRS "PAYER'S name, street address..., and telephone no." block.
    """
    lines: list[str] = [_payer_display_name(company)]

    if company.address_line1:
        lines.append(company.address_line1.strip())
    if company.address_line2:
        lines.append(company.address_line2.strip())

    city_state_zip = " ".join(
        p
        for p in [
            (company.city or "").strip(),
            (company.state or "").strip(),
            (company.postal_code or "").strip(),
        ]
        if p
    ).strip()
    if city_state_zip:
        lines.append(city_state_zip)

    if company.main_phone:
        lines.append(company.main_phone.strip())

    return "\n".join([l for l in lines if l]).strip()


def _latest_w9_or_404(*, user, contractor: Contractor) -> ContractorW9Submission:
    submission = (
        ContractorW9Submission.objects
        .filter(user=user, contractor=contractor)
        .order_by("-submitted_at", "-id")
        .first()
    )
    if not submission:
        raise Http404("No W-9 on file for this contractor.")
    return submission


def _recipient_from_w9(submission: ContractorW9Submission) -> tuple[str, str, str, str]:
    """
    Returns (recipient_name, street, city_state_zip, tin_digits) from the W-9 submission.
    """
    name = (submission.business_name or "").strip() or (submission.full_name or "").strip()
    if not name:
        name = "Recipient"

    street = (submission.address_line1 or "").strip()
    city_state_zip = (submission.address_line2 or "").strip()

    tin_digits = _normalize_tin((submission.tin or "").strip())
    if not tin_digits:
        raise Http404("W-9 on file is missing TIN.")

    return name, street, city_state_zip, tin_digits


def _contractor_box1_total(*, user, contractor: Contractor, tax_year: int) -> Decimal:
    """
    Sum contractor-linked EXPENSE transactions for the year.
    (Box 1 — Nonemployee compensation)
    """
    qs = Transaction.objects.filter(
        user=user,
        contractor=contractor,
        date__year=tax_year,
        trans_type__iexact="Expense",
    )
    total = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return abs(total)


def _no_store(resp: HttpResponse) -> HttpResponse:
    """Prevent browser/proxy caching of tax PDFs."""
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    return resp



def _get_or_create_1099_record(*, request: HttpRequest, contractor: Contractor, tax_year: int) -> Contractor1099:
    obj, _ = Contractor1099.objects.get_or_create(
        user=request.user,
        contractor=contractor,
        tax_year=tax_year,
        defaults={"generated_at": timezone.now()},
    )
    return obj


def _store_1099_pdfs(*, obj: Contractor1099, values: dict) -> Contractor1099:
    pdfs = render_1099nec_copy_b_and_1(
        values=values,
        layout=COPY_B_AND_1_LAYOUT(),
        output_mode="separate",
    )

    b_name = "1099_nec_copy_b.pdf"
    one_name = "1099_nec_copy_1.pdf"

    b_data = pdfs.get(b_name)
    one_data = pdfs.get(one_name)
    if not b_data or not one_data:
        raise Http404("Could not generate 1099 PDFs.")

    # Overwrite behavior: if a file already exists, delete it before saving new content
    # so S3 keys remain stable.
    if obj.copy_b_pdf:
        obj.copy_b_pdf.delete(save=False)
    if obj.copy_1_pdf:
        obj.copy_1_pdf.delete(save=False)

    obj.copy_b_pdf.save(b_name, ContentFile(b_data), save=False)
    obj.copy_1_pdf.save(one_name, ContentFile(one_data), save=False)

    obj.generated_at = timezone.now()
    obj.save()
    return obj


_ALLOWED_1099_FILES = {"1099_nec_copy_b.pdf", "1099_nec_copy_1.pdf"}



def _render_and_extract(*, values: dict, filename: str) -> bytes:
    """
    Render both Copy B and Copy 1 as separate PDFs, then return the requested one.
    """
    if filename not in _ALLOWED_1099_FILES:
        raise Http404("Invalid 1099 filename requested.")

    pdfs = render_1099nec_copy_b_and_1(
        values=values,
        layout=COPY_B_AND_1_LAYOUT(),
        output_mode="separate",
    )
    data = pdfs.get(filename)
    if not data:
        raise Http404(f"Could not generate {filename}.")
    return data




def _build_values_or_404(*, request: HttpRequest, contractor: Contractor, company: CompanyProfile, tax_year: int) -> dict:
    """
    Build the value payload for the 1099 renderer.
    Raises Http404 for missing required data (W-9 TIN, payer EIN, etc.).
    """
    w9 = _latest_w9_or_404(user=request.user, contractor=contractor)
    recipient_name, recipient_street, recipient_city, payee_tin = _recipient_from_w9(w9)

    payer_tin = _payer_tin_full(company)
    if not payer_tin:
        raise Http404("Payer EIN missing — update Company Profile.")

    box1_total = _contractor_box1_total(user=request.user, contractor=contractor, tax_year=tax_year)
    box7 = box7_state_income(company=company, contractor=contractor, box1_total=box1_total)

    return {
        # Payer
        "payer_block": _payer_block_lines(company),
        "payer_tin": payer_tin,

        # Recipient
        "recipient_tin": payee_tin,
        "recipient_name": recipient_name,
        "recipient_street": recipient_street,
        "recipient_city": recipient_city,

        # Year
        "tax_year": str(tax_year),

        # Amounts
        "box1": f"{box1_total:,.2f}",
        "box7": box7,
    }


def _serve_stored_pdf(*, request: HttpRequest, contractor: Contractor, tax_year: int, which: str) -> HttpResponse:
    obj = Contractor1099.objects.filter(user=request.user, contractor=contractor, tax_year=tax_year).first()

    if not obj or (which == "b" and not obj.copy_b_pdf) or (which == "1" and not obj.copy_1_pdf):
        # generate + store automatically
        company = _active_company_profile_or_404()
        values = _build_values_or_404(request=request, contractor=contractor, company=company, tax_year=tax_year)

        obj = obj or _get_or_create_1099_record(request=request, contractor=contractor, tax_year=tax_year)
        _store_1099_pdfs(obj=obj, values=values)

    f = obj.copy_b_pdf if which == "b" else obj.copy_1_pdf
    if not f:
        raise Http404("1099 PDF not available.")

    # Stream via filefield
    resp = HttpResponse(f.open("rb").read(), content_type="application/pdf")
    filename = "1099_nec_copy_b.pdf" if which == "b" else "1099_nec_copy_1.pdf"
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return _no_store(resp)


# --------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------


@login_required
def contractor_1099_copy_b_stored(request: HttpRequest, contractor_id: int, tax_year: int) -> HttpResponse:
    tax_year = _selected_year_or_404(tax_year)
    contractor = get_object_or_404(Contractor, pk=contractor_id, user=request.user, is_active=True)
    return _serve_stored_pdf(request=request, contractor=contractor, tax_year=tax_year, which="b")


@login_required
def contractor_1099_copy_1_stored(request: HttpRequest, contractor_id: int, tax_year: int) -> HttpResponse:
    tax_year = _selected_year_or_404(tax_year)
    contractor = get_object_or_404(Contractor, pk=contractor_id, user=request.user, is_active=True)
    return _serve_stored_pdf(request=request, contractor=contractor, tax_year=tax_year, which="1")


@login_required
def contractor_1099_copy_b(request: HttpRequest, contractor_id: int, tax_year: int) -> HttpResponse:
    tax_year = _selected_year_or_404(tax_year)

    contractor = get_object_or_404(
        Contractor,
        pk=contractor_id,
        user=request.user,
        is_active=True,
    )
    company = _active_company_profile_or_404()

    values = _build_values_or_404(request=request, contractor=contractor, company=company, tax_year=tax_year)

    filename = "1099_nec_copy_b.pdf"
    data = _render_and_extract(values=values, filename=filename)

    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return _no_store(resp)




@login_required
def contractor_1099_copy_1(request: HttpRequest, contractor_id: int, tax_year: int) -> HttpResponse:
    tax_year = _selected_year_or_404(tax_year)

    contractor = get_object_or_404(
        Contractor,
        pk=contractor_id,
        user=request.user,
        is_active=True,
    )
    company = _active_company_profile_or_404()

    values = _build_values_or_404(request=request, contractor=contractor, company=company, tax_year=tax_year)

    filename = "1099_nec_copy_1.pdf"
    data = _render_and_extract(values=values, filename=filename)

    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return _no_store(resp)




@login_required
@require_POST
def contractor_1099_generate_store(request: HttpRequest, contractor_id: int, tax_year: int) -> HttpResponse:
    tax_year = _selected_year_or_404(tax_year)
    contractor = get_object_or_404(Contractor, pk=contractor_id, user=request.user, is_active=True)
    company = _active_company_profile_or_404()

    values = _build_values_or_404(request=request, contractor=contractor, company=company, tax_year=tax_year)

    obj = _get_or_create_1099_record(request=request, contractor=contractor, tax_year=tax_year)
    _store_1099_pdfs(obj=obj, values=values)

    messages.success(request, f"Stored 1099-NEC PDFs for {tax_year}.")
    return redirect("money:contractor_detail", pk=contractor.pk)













@login_required
@require_POST
def contractor_1099_email_copy_b(request: HttpRequest, contractor_id: int, tax_year: int) -> HttpResponse:
    tax_year = _selected_year_or_404(tax_year)
    contractor = get_object_or_404(Contractor, pk=contractor_id, user=request.user, is_active=True)

    if not contractor.email:
        messages.error(request, "Contractor has no email address on file.")
        return redirect("money:contractor_detail", pk=contractor.pk)

    obj = Contractor1099.objects.filter(user=request.user, contractor=contractor, tax_year=tax_year).first()
    if not obj or not obj.copy_b_pdf:
        # Ensure it exists
        company = _active_company_profile_or_404()
        values = _build_values_or_404(request=request, contractor=contractor, company=company, tax_year=tax_year)
        obj = obj or _get_or_create_1099_record(request=request, contractor=contractor, tax_year=tax_year)
        _store_1099_pdfs(obj=obj, values=values)

    company = _active_company_profile_or_404()
    payer_name = _payer_display_name(company)

    subject = f"{tax_year} Form 1099-NEC (Copy B)"
    body = (
        f"Hello {contractor.display_name},\n\n"
        f"Attached is your {tax_year} Form 1099-NEC (Copy B) from {payer_name}.\n\n"
        "Thank you."
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        to=[contractor.email],
    )
    # attach file bytes
    pdf_bytes = obj.copy_b_pdf.open("rb").read()
    email.attach("1099-NEC_CopyB.pdf", pdf_bytes, "application/pdf")
    email.send(fail_silently=False)

    obj.emailed_at = timezone.now()
    obj.emailed_to = contractor.email
    obj.email_count = (obj.email_count or 0) + 1
    obj.save(update_fields=["emailed_at", "emailed_to", "email_count"])

    messages.success(request, f"Emailed Copy B to {contractor.email}.")
    return redirect("money:contractor_detail", pk=contractor.pk)
