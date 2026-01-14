from __future__ import annotations

import hashlib
from io import BytesIO

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from weasyprint import HTML

from money.models import InvoiceV2


def generate_invoice_pdf(invoice: InvoiceV2, *, force: bool = False) -> bool:
    """
    Generate (or regenerate) a PDF for an InvoiceV2 and attach it.

    Returns True if a PDF was generated, False if skipped.
    """

    if invoice.pdf_snapshot and not force:
        return False

    html = render_to_string(
        "money/invoices/invoice_v2_pdf.html",
        {
            "invoice": invoice,
        },
    )

    pdf_bytes = HTML(string=html).write_pdf()

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    filename = f"invoice_{invoice.invoice_number}.pdf"

    invoice.pdf_snapshot.save(
        filename,
        ContentFile(pdf_bytes),
        save=False,
    )

    invoice.pdf_sha256 = sha256
    invoice.pdf_snapshot_created_at = timezone.now()

    invoice._skip_pdf_regen = True  # escape hatch for signals
    invoice.save(
        update_fields=[
            "pdf_snapshot",
            "pdf_sha256",
            "pdf_snapshot_created_at",
        ]
    )


    return True
