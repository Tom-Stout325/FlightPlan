from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


IRS_W9_PDF_URL = "https://www.irs.gov/pub/irs-pdf/fw9.pdf"


@dataclass(frozen=True)
class W9EmailContext:
    contractor_name: str
    w9_portal_link: str
    support_email: str
    business_name: str
    business_phone: str
    irs_w9_pdf_link: str = IRS_W9_PDF_URL


def send_w9_request_email(*, to_email: str, ctx: W9EmailContext) -> None:
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "")
    subject = f"{prefix}Action Required: W-9 Needed for Tax Reporting"


    body = (
        f"Hi {ctx.contractor_name},\n\n"
        "We’re updating our records to ensure accurate year-end tax reporting (1099).\n\n"
        "You can complete your W-9 in whichever way is easiest:\n\n"
        "Option 1) Fill out our secure W-9 form online:\n"
        f"{ctx.w9_portal_link}\n\n"
        "Option 2) Download the official IRS Form W-9 PDF, complete it, then upload it securely:\n"
        f"IRS W-9 PDF: {ctx.irs_w9_pdf_link}\n"
        f"Upload portal: {ctx.w9_portal_link}\n\n"
        "For your security, please do not email tax information or your SSN/EIN.\n\n"
        f"If you have questions or believe you received this by mistake, contact us at {ctx.support_email}.\n\n"
        f"Thanks,\n{ctx.business_name}\n{ctx.business_phone}\n"
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "SERVER_EMAIL", None)
    if not from_email:
        # Fail loudly in dev so you set it
        raise ValueError("DEFAULT_FROM_EMAIL (or SERVER_EMAIL) must be set to send emails.")
    
    bcc = []
    brand_bcc = getattr(settings, "BRAND_BCC", None)
    if brand_bcc:
        bcc.append(brand_bcc)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[to_email],
        bcc=bcc,
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[to_email],
    )
    msg.send(fail_silently=False)
