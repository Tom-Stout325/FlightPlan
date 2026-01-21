from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction as db_tx
from django.db.models import Q
from django.db.models.functions import ExtractYear
from django.utils import timezone
from django.utils.text import slugify

from money.models import Event, Transaction, InvoiceV2


@dataclass(frozen=True)
class _EventYearKey:
    event_id: int
    year: int


def _normalize_years_arg(years_str: str | None) -> List[int]:
    if not years_str:
        current = timezone.localdate().year
        # sensible default window
        return [current - 3, current - 2, current - 1, current]

    years: List[int] = []
    for part in years_str.split(","):
        part = part.strip()
        if not part:
            continue
        years.append(int(part))
    return sorted(set(years))


def _base_slug_for_event(ev: Event) -> str:
    """
    Use existing slug if present (legacy "brainerd"), else slugify(title).
    We intentionally do NOT include year in the base slug.
    """
    s = (ev.slug or "").strip()
    if s:
        return s
    return slugify(ev.title or "")[:100] or f"event-{ev.pk}"


def _year_slug(base_slug: str, year: int) -> str:
    # Keep well under 100 chars. Reserve 5 for "-YYYY".
    base = (base_slug or "").strip()[:95]
    return f"{base}-{year}"


def _copy_event_to_year(ev: Event, year: int, slug: str) -> Event:
    """
    Clone a legacy event into a year-specific "Job" event.
    Normalizes legacy event_type values (e.g. 'race' -> 'commercial').
    Let save() generate job_number (unless you explicitly set it).
    """
    legacy_type = (ev.event_type or "").strip()

    # Legacy normalization: 'race' was folded into 'commercial'
    normalized_type = "commercial" if legacy_type == "race" else legacy_type

    new_ev = Event(
        user=ev.user,
        title=ev.title,
        client=ev.client,
        event_type=normalized_type,
        event_year=year,
        location_city=ev.location_city,
        location_address=ev.location_address,
        notes=ev.notes,
        slug=slug,
        job_number=None,  # let auto-generation run
    )
    
    if legacy_type == "race":
        # using self.stdout isn't available here; keep it silent or move normalization into handle() if you want logs
        pass

    new_ev.save()
    return new_ev


class Command(BaseCommand):
    help = (
        "Step 1: Create year-specific Job rows (Event records) for each legacy Event "
        "based on related Transaction.date and InvoiceV2.date years. "
        "Does NOT re-point invoices/transactions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            dest="years",
            default=None,
            help="Comma-separated years to consider (e.g. 2023,2024,2025,2026). "
                 "Default is current year and previous 3 years.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing changes.",
        )
        parser.add_argument(
            "--only-multi-year",
            action="store_true",
            help="Only process legacy events that have activity in 2+ distinct years.",
        )

    def handle(self, *args, **options):
        years = _normalize_years_arg(options.get("years"))
        dry_run = bool(options.get("dry_run"))
        only_multi_year = bool(options.get("only_multi_year"))

        self.stdout.write(self.style.MIGRATE_HEADING("Step 1: Create year-specific Jobs"))
        self.stdout.write(f"Years considered: {years}")
        self.stdout.write(f"Dry run: {dry_run}")
        self.stdout.write(f"Only multi-year legacy events: {only_multi_year}\n")

        # ---------------------------------------------------------------------
        # 1) Discover event-year usage from Transactions and Invoices
        # ---------------------------------------------------------------------
        years_set = set(years)

        tx_pairs = (
            Transaction.objects
            .filter(event__isnull=False)
            .annotate(y=ExtractYear("date"))
            .values_list("event_id", "y")
            .distinct()
        )
        inv_pairs = (
            InvoiceV2.objects
            .filter(event__isnull=False)
            .annotate(y=ExtractYear("date"))  # authoritative invoice year = invoice.date.year
            .values_list("event_id", "y")
            .distinct()
        )

        event_years: Dict[int, Set[int]] = {}
        for event_id, y in list(tx_pairs) + list(inv_pairs):
            if y is None:
                continue
            y = int(y)
            if y not in years_set:
                continue
            event_years.setdefault(int(event_id), set()).add(y)

        if not event_years:
            self.stdout.write(self.style.WARNING("No event/year usage found in the selected year window. Nothing to do."))
            return

        # Optionally restrict to multi-year legacy events
        if only_multi_year:
            event_years = {eid: ys for eid, ys in event_years.items() if len(ys) >= 2}
            if not event_years:
                self.stdout.write(self.style.WARNING("No multi-year legacy events found in the selected year window."))
                return

        legacy_events = (
            Event.objects
            .filter(id__in=list(event_years.keys()))
            .select_related("client", "user")
            .order_by("user_id", "title", "id")
        )

        # ---------------------------------------------------------------------
        # 2) For each legacy event, create missing year-specific job rows
        # ---------------------------------------------------------------------
        created = 0
        skipped_existing = 0
        skipped_same_row = 0

        # Preload existing year slugs to avoid per-row queries
        # We'll build expected slugs and check existence in one query.
        expected_slugs: Set[Tuple[int, str]] = set()  # (user_id, slug)
        for ev in legacy_events:
            base = _base_slug_for_event(ev)
            for y in sorted(event_years.get(ev.id, set())):
                expected_slugs.add((ev.user_id, _year_slug(base, y)))

        existing_slug_set: Set[Tuple[int, str]] = set(
            Event.objects
            .filter(
                Q(slug__isnull=False),
                # limit scan to users we touch by using user_id set:
                user_id__in={uid for uid, _ in expected_slugs},
            )
            .values_list("user_id", "slug")
        )

        # Now create any missing rows
        for ev in legacy_events:
            ys = sorted(event_years.get(ev.id, set()))
            if not ys:
                continue

            base = _base_slug_for_event(ev)

            self.stdout.write(self.style.HTTP_INFO(f"\nLegacy: #{ev.id} {ev.title!r} (user={ev.user_id}) years={ys}"))

            for y in ys:
                # If the legacy event itself is already the year-specific row (rare but possible),
                # don’t create a duplicate.
                if ev.event_year == y:
                    skipped_same_row += 1
                    self.stdout.write(f"  - {y}: skip (legacy row already has event_year={y})")
                    continue

                slug = _year_slug(base, y)
                if (ev.user_id, slug) in existing_slug_set:
                    skipped_existing += 1
                    self.stdout.write(f"  - {y}: exists (slug={slug})")
                    continue

                if dry_run:
                    created += 1
                    self.stdout.write(self.style.WARNING(f"  - {y}: would create (slug={slug})"))
                    continue

                # Write in a small atomic block per row to keep job_number counter safe
                # without locking the world for the whole run.
                with db_tx.atomic():
                    new_ev = _copy_event_to_year(ev, y, slug)
                created += 1
                existing_slug_set.add((ev.user_id, slug))
                self.stdout.write(self.style.SUCCESS(
                    f"  - {y}: created id={new_ev.id} slug={new_ev.slug} job_number={new_ev.job_number}"
                ))

        self.stdout.write("\n" + self.style.MIGRATE_HEADING("Summary"))
        self.stdout.write(f"Created: {created}")
        self.stdout.write(f"Skipped (already existed by slug): {skipped_existing}")
        self.stdout.write(f"Skipped (legacy row already had that year): {skipped_same_row}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run only — no changes written."))
        else:
            self.stdout.write(self.style.SUCCESS("\nDone. Step 1 complete: year-specific Job rows created."))
