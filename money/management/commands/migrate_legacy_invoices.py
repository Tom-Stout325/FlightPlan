from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from money.models import Invoice, InvoiceV2, InvoiceItemV2
from money.services.invoice_pdf import generate_invoice_pdf


# ---------------------------------------------------------------------
# Helper functions (module-level)
# ---------------------------------------------------------------------

def _legacy_or_default(value, default):
    return value if value not in (None, "") else default


def _normalize_qty(qty):
    """
    Legacy invoices often stored qty as NULL or 0.
    Treat missing or zero qty as 1.00.
    """
    if qty is None:
        return Decimal("1.00")
    try:
        qty = Decimal(qty)
    except Exception:
        return Decimal("1.00")
    return qty if qty > 0 else Decimal("1.00")


# ---------------------------------------------------------------------
# Management Command
# ---------------------------------------------------------------------

class Command(BaseCommand):
    help = "Migrate legacy Invoice + InvoiceItem records into InvoiceV2."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run without writing anything to the database.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit number of invoices processed (for testing).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options.get("limit")

        qs = (
            Invoice.objects
            .select_related("client", "event", "service", "client__user")
            .prefetch_related("items")
            .order_by("invoice_number")
        )

        if limit:
            qs = qs[:limit]

        self.stdout.write(self.style.NOTICE(f"Found {qs.count()} legacy invoices"))

        migrated = 0

        for legacy in qs:
            self.stdout.write(f"→ Migrating invoice {legacy.invoice_number}")

            if dry_run:
                continue

            with transaction.atomic():
                migrated += self._migrate_one_invoice(legacy)

        self.stdout.write(
            self.style.SUCCESS(f"Migration complete ({migrated} invoices)")
        )

    # -----------------------------------------------------------------

    def _migrate_one_invoice(self, legacy: Invoice) -> int:
        """
        Migrate a single legacy invoice + its items into InvoiceV2.
        """

        user = legacy.client.user

        # Guard against duplicates
        if InvoiceV2.objects.filter(
            user=user,
            invoice_number=legacy.invoice_number,
        ).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"  Skipping {legacy.invoice_number} (already migrated)"
                )
            )
            return 0

        # ----------------------------
        # Create InvoiceV2
        # ----------------------------
        invoice_v2 = InvoiceV2.objects.create(
            user=user,
            invoice_number=legacy.invoice_number,
            client=legacy.client,
            event=legacy.event,
            event_name=legacy.event_name,
            location=legacy.location,
            service=legacy.service,
            date=legacy.date,
            due=legacy.due,
            paid_date=legacy.paid_date,
            status=legacy.status,
            issued_at=legacy.issued_at,
            version=_legacy_or_default(legacy.version, 1),

            # Snapshot ("From") fields
            from_name=legacy.from_name or "",
            from_address=legacy.from_address or "",
            from_phone=legacy.from_phone or "",
            from_email=legacy.from_email or "",
            from_website=legacy.from_website or "",
            from_tax_id=legacy.from_tax_id or "",

            from_logo_url=legacy.from_logo_url or "",
            from_header_logo_max_width_px=_legacy_or_default(
                legacy.from_header_logo_max_width_px, 320
            ),

            from_terms=legacy.from_terms or "",
            from_net_days=_legacy_or_default(legacy.from_net_days, 30),
            from_footer_text=legacy.from_footer_text or "",

            from_currency=_legacy_or_default(legacy.from_currency, "USD"),
            from_locale=_legacy_or_default(legacy.from_locale, "en_US"),
            from_timezone=_legacy_or_default(
                legacy.from_timezone, "America/Indiana/Indianapolis"
            ),
        )

        # ----------------------------
        # Create line items
        # ----------------------------
        legacy_items = list(legacy.items.all())

        if not legacy_items and legacy.amount and legacy.amount != Decimal("0.00"):
            # Legacy invoice has a stored total but no item rows.
            InvoiceItemV2.objects.create(
                user=user,
                invoice=invoice_v2,
                description="Legacy invoice total",
                qty=Decimal("1.00"),
                price=legacy.amount,
                sub_cat=None,
                category=None,
            )
        else:
            for item in legacy_items:
                InvoiceItemV2.objects.create(
                    user=user,
                    invoice=invoice_v2,
                    description=item.description,
                    qty=_normalize_qty(item.qty),
                    price=item.price or Decimal("0.00"),
                    sub_cat=None,
                    category=None,
                )

        # ----------------------------
        # Verify totals
        # ----------------------------
        invoice_v2.update_amount(save=True)

        if invoice_v2.amount != legacy.amount:
            raise ValueError(
                f"Amount mismatch for invoice {legacy.invoice_number}: "
                f"{legacy.amount} != {invoice_v2.amount}"
            )

        # ----------------------------
        # Generate PDF
        # ----------------------------
        generate_invoice_pdf(invoice_v2, force=True)

        return 1
