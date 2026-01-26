from __future__ import annotations

from typing import Optional

from django.conf import settings

from money.models import CompanyProfile


def get_active_company_profile() -> Optional[CompanyProfile]:
    """
    Returns the active CompanyProfile if one exists; otherwise None.

    This assumes you enforce a single active profile per deployment.
    """
    return (
        CompanyProfile.objects
        .filter(is_active=True)
        .only(
            "legal_name", "display_name",
            "address_line1", "address_line2", "city", "state", "postal_code", "country",
            "main_phone", "support_email", "invoice_reply_to_email",
            "tax_id_ein",
        )
        .first()
    )


def payer_display_name(cp: CompanyProfile) -> str:
    return (cp.display_name or cp.legal_name).strip()


def payer_address_lines(cp: CompanyProfile) -> list[str]:
    lines: list[str] = []
    if cp.address_line1:
        lines.append(cp.address_line1)
    if cp.address_line2:
        lines.append(cp.address_line2)
    lines.append(f"{cp.city}, {cp.state} {cp.postal_code}".strip())
    if cp.country and cp.country != "United States":
        lines.append(cp.country)
    return [ln for ln in lines if ln and ln.strip()]


def payer_phone(cp: CompanyProfile) -> str:
    return (cp.main_phone or "").strip()


def payer_support_email(cp: CompanyProfile) -> str:
    # Prefer explicit support email; fall back to reply-to; fall back to DEFAULT_FROM_EMAIL
    return (cp.support_email or cp.invoice_reply_to_email or settings.DEFAULT_FROM_EMAIL).strip()


def payer_tin_display(cp: CompanyProfile) -> str:
    # WARNING: This is displayed on recipient copy. Use exactly what you want shown.
    return (cp.tax_id_ein or "").strip()
