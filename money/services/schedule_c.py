# money/services/schedule_c.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Dict, Any
from collections import defaultdict

from django.db.models import (
    F,
    Sum,
    Value,
    ExpressionWrapper,
    DecimalField,
)
from django.db.models.functions import Coalesce

from money.models import Transaction, Miles, MileageRate


# Categories that should NOT count as income on Schedule C line 1
EXCLUDED_INCOME_CATEGORIES = ["Equipment Sale"]


# =====================================================================
# DATA STRUCTURE FOR OUTPUT
# =====================================================================

@dataclass
class ScheduleCAmounts:
    # Part I — Income
    line_1: Decimal = Decimal("0.00")   # Gross receipts or sales
    line_2: Decimal = Decimal("0.00")   # Returns and allowances (manual)
    line_3: Decimal = Decimal("0.00")   # line 1 – line 2
    line_4: Decimal = Decimal("0.00")   # Cost of goods sold
    line_5: Decimal = Decimal("0.00")   # line 3 – line 4
    line_6: Decimal = Decimal("0.00")   # Other income (manual)
    line_7: Decimal = Decimal("0.00")   # line 5 + line 6

    # Part II — Expenses
    line_8: Decimal = Decimal("0.00")   # Advertising
    line_9: Decimal = Decimal("0.00")   # Car & truck (mileage dollars)
    line_10: Decimal = Decimal("0.00")  # Commissions & fees
    line_11: Decimal = Decimal("0.00")  # Contract labor
    line_12: Decimal = Decimal("0.00")  # Depletion (manual)
    line_13: Decimal = Decimal("0.00")  # Depreciation (manual)
    line_14: Decimal = Decimal("0.00")  # Employee benefit programs (manual)
    line_15: Decimal = Decimal("0.00")  # Insurance (other than health)
    line_16a: Decimal = Decimal("0.00") # Mortgage interest (manual)
    line_16b: Decimal = Decimal("0.00") # Other interest (manual)
    line_17: Decimal = Decimal("0.00")  # Legal & professional services
    line_18: Decimal = Decimal("0.00")  # Office expense
    line_19: Decimal = Decimal("0.00")  # Pension/profit-sharing (manual)
    line_20a: Decimal = Decimal("0.00") # Rent – vehicles, machinery, equipment
    line_20b: Decimal = Decimal("0.00") # Rent – other business property
    line_21: Decimal = Decimal("0.00")  # Repairs & maintenance
    line_22: Decimal = Decimal("0.00")  # Supplies
    line_23: Decimal = Decimal("0.00")  # Taxes & licenses
    line_24: Decimal = Decimal("0.00")  # Travel + meals combined
    line_24a: Decimal = Decimal("0.00") # Travel
    line_24b: Decimal = Decimal("0.00") # Meals (50% deductible amount)
    line_25: Decimal = Decimal("0.00")  # Utilities
    line_26: Decimal = Decimal("0.00")  # Wages
    line_27a: Decimal = Decimal("0.00") # Other expenses (from Part V)
    line_27b: Decimal = Decimal("0.00") # Reserved / special credits (manual)
    line_28: Decimal = Decimal("0.00")  # Total expenses
    line_29: Decimal = Decimal("0.00")  # Tentative profit (loss)
    line_30: Decimal = Decimal("0.00")  # Business use of home (manual)
    line_31: Decimal = Decimal("0.00")  # Net profit (loss)

    # Part III — optional inventory / COGS detail
    line_35: Decimal = Decimal("0.00")
    line_36: Decimal = Decimal("0.00")
    line_37: Decimal = Decimal("0.00")
    line_38: Decimal = Decimal("0.00")
    line_39: Decimal = Decimal("0.00")
    line_40: Decimal = Decimal("0.00")
    line_41: Decimal = Decimal("0.00")
    line_42: Decimal = Decimal("0.00")

    # Part V — total other expenses
    line_48_total: Decimal = Decimal("0.00")


# =====================================================================
# MAIN SERVICE
# =====================================================================

def get_schedule_c_totals(user, year: int) -> Dict[str, Any]:
    """
    Build Schedule C totals using the SAME logic as financial_statement /
    get_summary_data:

    - Meals → 50% deductible
    - Fuel + personal vehicle → excluded
    - Equipment Sale income excluded
    - Group by Category.schedule_c_line
    - Add separate mileage dollars from Miles/MileageRate for line 9
    - Build Part V detail rows for schedule_c_line == '27a'
    """
    amounts = ScheduleCAmounts()

    # ------------------------------------------------------------------
    # 1. Pull all transactions for the year with category/sub_cat loaded
    # ------------------------------------------------------------------
    qs = (
        Transaction.objects
        .filter(user=user, date__year=year)
        .select_related("sub_cat__category")
    )

    income_by_line = defaultdict(lambda: Decimal("0.00"))
    expense_by_line = defaultdict(lambda: Decimal("0.00"))
    part_v_map: Dict[int, Dict[str, Any]] = {}  # sub_cat_id -> {"id", "name", "total"}

    for t in qs:
        category = t.sub_cat.category if (t.sub_cat and t.sub_cat.category_id) else None
        cat_name = category.category if category else None
        sched_line = (category.schedule_c_line or "").strip() if getattr(category, "schedule_c_line", None) else ""

        # If this category isn't mapped to any Schedule C line, skip it
        if not sched_line:
            continue

        # --- Match financial_statement adjustments ---
        is_meals = getattr(t.sub_cat, "slug", None) == "meals"
        is_fuel = getattr(t.sub_cat, "slug", None) == "fuel"
        is_personal_vehicle = getattr(t, "transport_type", None) == "personal_vehicle"

        if is_meals:
            amount = (t.amount * Decimal("0.5")).quantize(Decimal("0.01"))
        elif is_fuel and is_personal_vehicle:
            amount = Decimal("0.00")
        else:
            amount = t.amount

        # --- Income vs Expense routing ---
        if t.trans_type == "Income":
            if cat_name in EXCLUDED_INCOME_CATEGORIES:
                continue
            income_by_line[sched_line] += amount
        else:
            expense_by_line[sched_line] += amount

            # Build Part V detail for "Other expenses" (27a)
            if sched_line == "27a" and t.sub_cat_id:
                entry = part_v_map.setdefault(
                    t.sub_cat_id,
                    {
                        "id": t.sub_cat_id,
                        "name": t.sub_cat.sub_cat if t.sub_cat else "Uncategorized",
                        "total": Decimal("0.00"),
                    },
                )
                entry["total"] += amount

    # Helper to read a line safely
    def g(d: Dict[str, Decimal], key: str) -> Decimal:
        return d.get(key, Decimal("0.00"))

    # ==========================================================
    # PART I — INCOME
    # ==========================================================

    # Line 1 – Gross receipts or sales
    amounts.line_1 = g(income_by_line, "1")

    # Line 2 – manual for now (returns/allowances)

    # Line 3 – line 1 minus line 2
    amounts.line_3 = amounts.line_1 - amounts.line_2

    # Line 4 – Cost of goods sold (if you map any category to schedule_c_line "4")
    amounts.line_4 = g(expense_by_line, "4")

    # Line 5 – line 3 minus line 4
    amounts.line_5 = amounts.line_3 - amounts.line_4

    # Line 6 – Other income (manual)

    # Line 7 – Gross income (line 5 + line 6)
    amounts.line_7 = amounts.line_5 + amounts.line_6

    # ==========================================================
    # PART II — EXPENSES (category-based lines)
    # ==========================================================

    amounts.line_8  = g(expense_by_line, "8")
    # line_9 handled below (mileage)
    amounts.line_10 = g(expense_by_line, "10")
    amounts.line_11 = g(expense_by_line, "11")
    # 12, 13, 14 are manual
    amounts.line_15 = g(expense_by_line, "15")
    # 16a, 16b manual
    amounts.line_17 = g(expense_by_line, "17")
    amounts.line_18 = g(expense_by_line, "18")
    # 19 manual
    amounts.line_20a = g(expense_by_line, "20a")
    amounts.line_20b = g(expense_by_line, "20b")
    amounts.line_21 = g(expense_by_line, "21")
    amounts.line_22 = g(expense_by_line, "22")
    amounts.line_23 = g(expense_by_line, "23")
    amounts.line_25 = g(expense_by_line, "25")
    amounts.line_26 = g(expense_by_line, "26")

    # Travel / Meals
    amounts.line_24a = g(expense_by_line, "24a")
    amounts.line_24b = g(expense_by_line, "24b")
    amounts.line_24 = amounts.line_24a + amounts.line_24b

    # ==========================================================
    # MILEAGE — line 9 (Car & truck expenses)
    # ==========================================================

    try:
        rate_obj = MileageRate.objects.first()
        rate = (
            Decimal(str(rate_obj.rate))
            if rate_obj and rate_obj.rate is not None
            else Decimal("0.70")
        )
    except Exception:
        rate = Decimal("0.70")

    miles_qs = Miles.objects.filter(
        user=user,
        date__year=year,
        mileage_type="Taxable",
    )

    miles_expr = ExpressionWrapper(
        Coalesce(F("total"), F("end") - F("begin"), Value(0)),
        output_field=DecimalField(max_digits=12, decimal_places=1),
    )

    annotated_miles = miles_qs.annotate(miles=miles_expr)
    totals = annotated_miles.aggregate(total_miles=Sum("miles"))
    total_miles = totals["total_miles"] or Decimal("0.00")
    mileage_dollars = (total_miles * rate).quantize(Decimal("0.01"))

    amounts.line_9 = mileage_dollars

    # ==========================================================
    # PART V — OTHER EXPENSES (line 27a, 48)
    # ==========================================================

    amounts.line_27a = g(expense_by_line, "27a")
    amounts.line_48_total = amounts.line_27a

    # Turn Part V map into a sorted list for the template
    part_v_rows = sorted(part_v_map.values(), key=lambda r: r["name"].lower())

    # ==========================================================
    # LINE 28 – TOTAL EXPENSES
    # (add all auto + manual expense lines 8–27a/27b)
    # ==========================================================

    auto_expense_components = [
        amounts.line_8,
        amounts.line_9,
        amounts.line_10,
        amounts.line_11,
        amounts.line_12,   # manual
        amounts.line_13,   # manual
        amounts.line_14,   # manual
        amounts.line_15,
        amounts.line_16a,  # manual
        amounts.line_16b,  # manual
        amounts.line_17,
        amounts.line_18,
        amounts.line_19,   # manual
        amounts.line_20a,
        amounts.line_20b,
        amounts.line_21,
        amounts.line_22,
        amounts.line_23,
        amounts.line_24,
        amounts.line_25,
        amounts.line_26,
        amounts.line_27a,
        amounts.line_27b,  # manual
    ]
    amounts.line_28 = sum(auto_expense_components)

    # ==========================================================
    # Lines 29–31
    # ==========================================================

    # Tentative profit (loss): line 7 – line 28
    amounts.line_29 = amounts.line_7 - amounts.line_28

    # line_30 remains manual (business use of home)

    # Net profit (loss): line 29 – line 30
    amounts.line_31 = amounts.line_29 - amounts.line_30

    # ------------------------------------------------------------------
    # Build final dict for the template
    # ------------------------------------------------------------------
    data = asdict(amounts)
    data["part_v_rows"] = part_v_rows
    return data
