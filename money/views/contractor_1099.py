# money/views/contractor_1099.py
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from money.constants.state_1099 import STATES_REQUIRE_BOX7_STATE_INCOME
from money.models import CompanyProfile, Contractor, ContractorW9Submission, Transaction
from money.utils.pdf_1099nec import COPY_B_AND_1_LAYOUT, render_1099nec_copy_b_and_1


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


# --------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------

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
