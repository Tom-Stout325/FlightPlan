from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.db.models.functions import Coalesce

from money.models import Transaction


@dataclass(frozen=True)
class ScheduleCLineTotals:
    line: str
    total: Decimal
    breakdown: list[dict[str, Any]]


DEFAULT_MEALS_SUBCAT_SLUGS = {"meals"}


def build_schedule_c_context(*, user, year: int) -> dict[str, Any]:
    """
    Data-driven Schedule C aggregation using:
    - SubCategory.include_in_tax_reports
    - SubCategory.schedule_c_line

    Special rule:
    - SubCategory slug "meals" is 50% deductible (refunds reduce deductible too)
    """
    qs = (
        Transaction.objects
        .filter(user=user, date__year=year, trans_type="Expense")
        .select_related("sub_cat", "sub_cat__category")
        .filter(sub_cat__isnull=False)
        .filter(sub_cat__include_in_tax_reports=True)
        .exclude(sub_cat__schedule_c_line__isnull=True)
        .exclude(sub_cat__schedule_c_line__exact="")
    )

    rows = (
        qs.values(
            "sub_cat__sub_cat",
            "sub_cat__slug",
            "sub_cat__schedule_c_line",
            "sub_cat__category__category",
        )
        .annotate(total=Coalesce(Sum("amount"), Decimal("0.00")))
        .order_by("sub_cat__schedule_c_line", "sub_cat__category__category", "sub_cat__sub_cat")
    )

    meals_rate = Decimal("0.50")

    adjusted_rows: list[dict[str, Any]] = []
    for r in rows:
        raw = r["total"] or Decimal("0.00")
        deductible = raw

        if (r["sub_cat__slug"] or "") in DEFAULT_MEALS_SUBCAT_SLUGS:
            deductible = raw * meals_rate

        adjusted_rows.append(
            {
                "line": (r["sub_cat__schedule_c_line"] or "").strip(),
                "category": r["sub_cat__category__category"] or "",
                "sub_cat": r["sub_cat__sub_cat"] or "",
                "sub_cat_slug": r["sub_cat__slug"] or "",
                "raw_total": raw,
                "deductible_total": deductible,
            }
        )

    line_totals: dict[str, Decimal] = {}
    line_breakdown: dict[str, list[dict[str, Any]]] = {}

    for r in adjusted_rows:
        line = r["line"]
        if not line:
            continue
        line_totals[line] = line_totals.get(line, Decimal("0.00")) + (r["deductible_total"] or Decimal("0.00"))
        line_breakdown.setdefault(line, []).append(r)

    lines = [
        ScheduleCLineTotals(
            line=line,
            total=line_totals[line].quantize(Decimal("0.01")),
            breakdown=line_breakdown[line],
        )
        for line in sorted(line_totals.keys())
    ]

    grand_total = sum((l.total for l in lines), Decimal("0.00")).quantize(Decimal("0.01"))

    return {
        "year": year,
        "lines": lines,
        "grand_total": grand_total,
        "meals_rate": meals_rate,
    }
