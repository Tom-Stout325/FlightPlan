from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, List

from django.conf import settings
from django.core.files.storage import default_storage
from django.urls import reverse, NoReverseMatch
from django.utils.functional import cached_property

from money.models import InvoiceV2, Invoice


from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from django.utils.functional import cached_property








@dataclass
class UnifiedInvoiceRow:
    """
    Normalised representation of all invoice sources so the list template
    can render a single table regardless of where the data came from.

    kind:
        'v2'           -> InvoiceV2 instance
        'legacy_model' -> legacy Invoice instance in the DB
        'legacy_file'  -> PDF-only legacy invoice on storage
    """

    kind: str
    id: str  # e.g. "v2-9", "legacy-12", "file-250101"

    invoice_number: str
    client_name: str
    event_name: Optional[str]
    issue_date: Optional[date]
    total_amount: Optional[Decimal]

    # Primary URLs used by the list template
    detail_url: str
    review_url: Optional[str] = None  # ✅ ADD: points to invoice_review / invoice_v2_review

    # Optional extras
    pdf_url: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    due_date: Optional[date] = None

    @cached_property
    def is_v2(self) -> bool:
        return self.kind == "v2"

    @cached_property
    def is_legacy_model(self) -> bool:
        return self.kind == "legacy_model"

    @cached_property
    def is_legacy_file(self) -> bool:
        return self.kind == "legacy_file"










# ----------------------------------------------------------------------
# V2 invoices
# ----------------------------------------------------------------------
def load_v2_invoices(request) -> List[UnifiedInvoiceRow]:
    """
    Build rows for all InvoiceV2 objects (no filtering here; filters are
    applied in the view).
    """
    qs = (
        InvoiceV2.objects
        .select_related("client", "event")
        .order_by("-date", "-pk")
    )

    rows: List[UnifiedInvoiceRow] = []

    for inv in qs:
        # Client display
        client_name = "—"
        client = getattr(inv, "client", None)
        if client is not None:
            client_name = (
                getattr(client, "business", None)
                or getattr(client, "name", None)
                or str(client)
            )

  
        event_name = None
        event = getattr(inv, "event", None)
        if event is not None:
            event_name = getattr(event, "title", None) or str(event)
        else:
            event_name = getattr(inv, "event_name", None)

        # Dates / amounts
        issue_date = (
            getattr(inv, "date", None)
            or getattr(inv, "issue_date", None)
        )

        total_amount = (
            getattr(inv, "amount", None)
            or getattr(inv, "total_amount", None)
        )

        status = getattr(inv, "status", None)
        location = getattr(inv, "location", None)
        due_date = getattr(inv, "due", None)

        # URLs
        try:
            detail_url = reverse("money:invoice_v2_detail", args=[inv.pk])
        except NoReverseMatch:
            detail_url = "#"

        try:
            review_url = reverse("money:invoice_v2_review", args=[inv.pk])
        except NoReverseMatch:
            review_url = detail_url

        try:
            pdf_url = reverse("money:invoice_v2_pdf", args=[inv.pk])
        except NoReverseMatch:
            pdf_url = None

        rows.append(
            UnifiedInvoiceRow(
                kind="v2",
                id=f"v2-{inv.pk}",
                invoice_number=str(getattr(inv, "invoice_number", None) or f"{inv.pk}"),
                client_name=client_name or "—",
                event_name=event_name,
                issue_date=issue_date,
                total_amount=total_amount,
                detail_url=detail_url,
                review_url=review_url,   
                pdf_url=pdf_url,
                status=status,
                location=location or None,
                due_date=due_date,
            )
        )

    return rows








# ----------------------------------------------------------------------
# Legacy DB invoices (old Invoice model)
# ----------------------------------------------------------------------
def load_legacy_model_invoices(request) -> List[UnifiedInvoiceRow]:
    """
    Legacy invoices that still exist in the old Invoice model.
    """
    qs = (
        Invoice.objects
        .select_related("client", "event")
        .order_by("-date", "-pk")
    )

    rows: List[UnifiedInvoiceRow] = []

    for inv in qs:
        client_name = "—"
        client = getattr(inv, "client", None)
        if client is not None:
            client_name = (
                getattr(client, "business", None)
                or getattr(client, "name", None)
                or str(client)
            )

        # Prefer related Event.title, then event_name
        event_name = None
        event = getattr(inv, "event", None)
        if event is not None:
            event_name = getattr(event, "title", None) or str(event)
        else:
            event_name = getattr(inv, "event_name", None)

        issue_date = (
            getattr(inv, "date", None)
            or getattr(inv, "issue_date", None)
        )

        total_amount = (
            getattr(inv, "amount", None)
            or getattr(inv, "total_amount", None)
        )

        pdf_url = getattr(inv, "pdf_url", None) or None
        status = getattr(inv, "status", None)
        location = getattr(inv, "location", None)
        due_date = getattr(inv, "due", None)

        # Existing legacy detail view (keep it)
        try:
            detail_url = reverse("money:legacy_invoice_detail", args=[inv.pk])
        except NoReverseMatch:
            detail_url = "#"

        # ✅ IMPORTANT: legacy review view (this is what you want back)
        try:
            review_url = reverse("money:invoice_review", args=[inv.pk])
        except NoReverseMatch:
            review_url = detail_url

        rows.append(
            UnifiedInvoiceRow(
                kind="legacy_model",
                id=f"legacy-{inv.pk}",
                invoice_number=str(getattr(inv, "invoice_number", None) or f"{inv.pk}"),
                client_name=client_name or "—",
                event_name=event_name,
                issue_date=issue_date,
                total_amount=total_amount,
                detail_url=detail_url,
                review_url=review_url,   # ✅ ADD
                pdf_url=pdf_url,
                status=status,
                location=location or None,
                due_date=due_date,
            )
        )

    return rows








# ----------------------------------------------------------------------
# Legacy PDF-only files (no DB record)
# ----------------------------------------------------------------------
def load_legacy_files(request) -> List[UnifiedInvoiceRow]:
    """
    Legacy PDFs that are *not* in the DB.

    We assume they live under DEFAULT_FILE_STORAGE at `LEGACY_INVOICE_DIR`.

    Example settings:
        LEGACY_INVOICE_DIR = "legacy_invoices/"
    """
    legacy_dir = getattr(settings, "LEGACY_INVOICE_DIR", "legacy_invoices/")
    rows: List[UnifiedInvoiceRow] = []

    try:
        # listdir returns (subdirs, files)
        _, file_list = default_storage.listdir(legacy_dir)
    except Exception:
        return rows

    for filename in file_list:
        if not filename.lower().endswith(".pdf"):
            continue

        path = f"{legacy_dir}{filename}"

        if not default_storage.exists(path):
            continue

        try:
            pdf_url = default_storage.url(path)
        except Exception:
            pdf_url = None

        base_name = filename.rsplit(".", 1)[0]

        try:
            detail_url = reverse(
                "money:legacy_file_invoice_detail",
                kwargs={"filename": path},
            )
        except NoReverseMatch:
            detail_url = "#"

        rows.append(
            UnifiedInvoiceRow(
                kind="legacy_file",
                id=f"file-{base_name}",
                invoice_number=base_name,
                client_name="(Legacy PDF only)",
                event_name=None,
                issue_date=None,
                total_amount=None,
                detail_url=detail_url,
                pdf_url=pdf_url,
                status=None,
                location=None,
                due_date=None,
            )
        )

    return rows
