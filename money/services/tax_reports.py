# money/services/tax_reports.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import (
    Case,
    When,
    Value,
    F,
    Sum,
    DecimalField,
    ExpressionWrapper,
    Q,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from money.models import Transaction


TWO_DP = DecimalField(max_digits=20, decimal_places=2)


# -------------------------
# Year selection helper
# -------------------------
@dataclass(frozen=True)
class YearContext:
    selected_year: int
    current_year: int


def get_selected_year(request, start_year: int = 2023) -> dict:
    """
    Returns: dict ready for templates:
      - selected_year
      - year_range
      - current_year
    """
    current_year = timezone.localdate().year
    year_param = (request.GET.get("year") or "").strip()
    selected_year = int(year_param) if year_param.isdigit() else current_year

    return {
        "selected_year": selected_year,
        "current_year": current_year,
        "year_range": range(start_year, current_year + 1),
    }


# -------------------------
# Base querysets
# -------------------------
def tax_base_qs(user, year: int):
    """
    Shared base queryset for tax reports.
    - Includes select_related for category + sub_cat for fewer queries
    - Excludes subcategories that are explicitly excluded from tax reports
      (include_in_tax_reports=False)
    """
    return (
        Transaction.objects.filter(user=user, date__year=year)
        .select_related("category", "sub_cat")
        .filter(Q(sub_cat__isnull=True) | Q(sub_cat__include_in_tax_reports=True))
    )


def income_qs(qs):
    return qs.filter(trans_type=Transaction.INCOME)


def expense_qs(qs):
    return qs.filter(trans_type=Transaction.EXPENSE)


# -------------------------
# Tax adjustment expressions
# -------------------------
def tax_amount_expressions(
    meals_slug: str = "meals",
    personal_fuel_slug: str = "fuel",
):
    """
    Returns 2 expressions:
      - net_expr: raw amount (used for “Net Income”)
      - taxable_expr: tax-adjusted expense amount

    Adjustments implemented:
      1) Meals (sub_cat.slug == 'meals'): 50% deductible
      2) Personal vehicle fuel (sub_cat.slug == 'fuel' AND transport_type == 'personal_vehicle'):
         excluded from taxable expenses (0.00), but still counts in net expenses
    """
    net_expr = F("amount")

    meals_expr = ExpressionWrapper(
        F("amount") * Value(Decimal("0.50")),
        output_field=TWO_DP,
    )

    taxable_expr = Case(
        # Exclude personal-vehicle fuel from taxable (but keep in net)
        When(
            Q(sub_cat__slug=personal_fuel_slug) & Q(transport_type="personal_vehicle"),
            then=Value(Decimal("0.00")),
        ),
        # Meals 50%
        When(Q(sub_cat__slug=meals_slug), then=meals_expr),
        # Default: full amount
        default=F("amount"),
        output_field=TWO_DP,
    )

    return net_expr, taxable_expr


def sum_expr(qs, expr):
    """
    Aggregate helper that returns Decimal 0.00 if empty.
    """
    return qs.aggregate(
        total=Coalesce(
            Sum(expr, output_field=TWO_DP),
            Value(Decimal("0.00")),
            output_field=TWO_DP,
        )
    )["total"]


# -------------------------
# Schedule C line expression
# -------------------------
def schedule_c_line_expr():
    """
    Choose the Schedule C line in this priority:
      1) SubCategory.schedule_c_line
      2) Category.schedule_c_line
      3) None

    Useful for grouping in Schedule C summary.
    """
    return Coalesce(F("sub_cat__schedule_c_line"), F("category__schedule_c_line"))
