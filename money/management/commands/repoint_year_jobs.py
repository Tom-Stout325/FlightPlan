# money/management/commands/repoint_year_jobs.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction as db_tx
from django.db.models import Q
from django.db.models.functions import ExtractYear
from django.utils.text import slugify
from django.utils import timezone

from money.models import Event, Transaction, InvoiceV2


YEAR_SLUG_RE = re.compile(r".*-\d{4}$")


def _normalize_years_arg(years_str: str | None) -> List[int]:
    if not years_str:
        current = timezone.localdate().year
        return [current - 3, current - 2, current - 1, current]
    years: List[int] = []
    for part in years_str.split(","):
        part = part.strip()
        if not part:
            continue
        years.append(int(part))
    return sorted(set(years))


def _is_year_slug(slug: str | None) -> bool:
    s = (slug or "").strip()
    return bool(s) and bool(YEAR_SLUG_RE.match(s))


def _base_slug_for_event(ev: Event) -> str:
    """
    Must match Step 1 behavior:
    - Use existing slug if present, else slugify(title).
    - Do NOT include year.
    """
    s = (ev.slug or "").strip()
    if s:
        return s
    return slugify(ev.title or "")[:100] or f"event-{ev.pk}"


def _year_slug(base_slug: str, year: int) -> str:
    base = (base_slug or "").strip()[:95]
    return f"{base}-{year}"


@dataclass
class Stats:
    scanned_tx: int = 0
    would_move_tx: int = 0
    moved_tx: int = 0
    missing_target_tx: int = 0
    skipped_tx_already_year_job: int = 0

    scanned_inv: int = 0
    would_move_inv: int = 0
    moved_inv: int = 0
    missing_target_inv: int = 0
    skipped_inv_already_year_job: int = 0


class Command(BaseCommand):
    help = (
        "Step 2: Re-point Transaction.event and InvoiceV2.event to the correct year-specific Job "
        "(Event row) using Transaction.date.year and InvoiceV2.date.year. "
        "Uses slug mapping base_slug + '-YYYY'. Safe to rerun."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            dest="years",
            default=None,
            help="Comma-separated years to repoint (e.g. 2023,2024,2025). Default is current and previous 3 years.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing anything.",
        )
        parser.add_argument(
            "--batch-size",
            dest="batch_size",
            type=int,
            default=500,
            help="How many rows to bulk update per batch (default 500).",
        )

    def handle(self, *args, **options):
        years = _normalize_years_arg(options.get("years"))
        years_set = set(years)
        dry_run = bool(options.get("dry_run"))
        batch_size = int(options.get("batch_size") or 500)

        self.stdout.write(self.style.MIGRATE_HEADING("Step 2: Re-point to year-specific Jobs"))
        self.stdout.write(f"Years: {years}")
        self.stdout.write(f"Dry run: {dry_run}")
        self.stdout.write(f"Batch size: {batch_size}\n")

        stats = Stats()

        # ------------------------------------------------------------------
        # Build a fast lookup: (user_id, target_slug) -> target_event_id
        # ------------------------------------------------------------------
        # Only year-specific rows (slugs that end in -YYYY) are targets.
        year_jobs = Event.objects.filter(slug__regex=r".*-\d{4}$").values_list("user_id", "slug", "id")
        target_by_user_slug: Dict[Tuple[int, str], int] = {(uid, slug): eid for uid, slug, eid in year_jobs}

        # ------------------------------------------------------------------
        # Repoint Transactions
        # ------------------------------------------------------------------
        tx_qs = (
            Transaction.objects
            .filter(event__isnull=False)
            .annotate(y=ExtractYear("date"))
            .filter(y__in=years)
            .select_related("event")
            .only("id", "date", "event_id", "event__id", "event__slug", "event__title", "event__user_id")
        )

        tx_to_update: List[Transaction] = []

        for tx in tx_qs.iterator(chunk_size=2000):
            stats.scanned_tx += 1

            year = tx.date.year
            ev = tx.event
            if not ev:
                continue

            # If already points to a year-specific job, leave it alone
            if _is_year_slug(ev.slug):
                stats.skipped_tx_already_year_job += 1
                continue

            base = _base_slug_for_event(ev)
            target_slug = _year_slug(base, year)
            target_id = target_by_user_slug.get((ev.user_id, target_slug))

            if not target_id:
                stats.missing_target_tx += 1
                continue

            if tx.event_id != target_id:
                stats.would_move_tx += 1
                if not dry_run:
                    tx.event_id = target_id
                    tx_to_update.append(tx)

            # Flush in batches
            if not dry_run and len(tx_to_update) >= batch_size:
                Transaction.objects.bulk_update(tx_to_update, ["event"])
                stats.moved_tx += len(tx_to_update)
                tx_to_update.clear()

        if not dry_run and tx_to_update:
            Transaction.objects.bulk_update(tx_to_update, ["event"])
            stats.moved_tx += len(tx_to_update)
            tx_to_update.clear()

        # ------------------------------------------------------------------
        # Repoint Invoices
        # ------------------------------------------------------------------
        inv_qs = (
            InvoiceV2.objects
            .filter(event__isnull=False)
            .annotate(y=ExtractYear("date"))   # authoritative invoice year = InvoiceV2.date.year
            .filter(y__in=years)
            .select_related("event")
            .only("id", "date", "event_id", "event__id", "event__slug", "event__title", "event__user_id")
        )

        inv_to_update: List[InvoiceV2] = []

        for inv in inv_qs.iterator(chunk_size=2000):
            stats.scanned_inv += 1

            year = inv.date.year
            ev = inv.event
            if not ev:
                continue

            if _is_year_slug(ev.slug):
                stats.skipped_inv_already_year_job += 1
                continue

            base = _base_slug_for_event(ev)
            target_slug = _year_slug(base, year)
            target_id = target_by_user_slug.get((ev.user_id, target_slug))

            if not target_id:
                stats.missing_target_inv += 1
                continue

            if inv.event_id != target_id:
                stats.would_move_inv += 1
                if not dry_run:
                    inv.event_id = target_id
                    inv_to_update.append(inv)

            if not dry_run and len(inv_to_update) >= batch_size:
                InvoiceV2.objects.bulk_update(inv_to_update, ["event"])
                stats.moved_inv += len(inv_to_update)
                inv_to_update.clear()

        if not dry_run and inv_to_update:
            InvoiceV2.objects.bulk_update(inv_to_update, ["event"])
            stats.moved_inv += len(inv_to_update)
            inv_to_update.clear()

        # ------------------------------------------------------------------
        # Output summary
        # ------------------------------------------------------------------
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("Summary"))

        self.stdout.write(f"Transactions scanned: {stats.scanned_tx}")
        self.stdout.write(f"Transactions already on year-jobs: {stats.skipped_tx_already_year_job}")
        self.stdout.write(f"Transactions missing target job: {stats.missing_target_tx}")
        self.stdout.write(f"Transactions would move: {stats.would_move_tx}")
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Transactions moved: {stats.moved_tx}"))

        self.stdout.write("")
        self.stdout.write(f"Invoices scanned: {stats.scanned_inv}")
        self.stdout.write(f"Invoices already on year-jobs: {stats.skipped_inv_already_year_job}")
        self.stdout.write(f"Invoices missing target job: {stats.missing_target_inv}")
        self.stdout.write(f"Invoices would move: {stats.would_move_inv}")
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Invoices moved: {stats.moved_inv}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run only — no changes written."))
        else:
            self.stdout.write(self.style.SUCCESS("\nDone. Step 2 complete: records re-pointed to year-specific Jobs."))

