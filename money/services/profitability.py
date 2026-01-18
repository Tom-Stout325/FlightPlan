# money/services/profitability.py
from __future__ import annotations

from decimal import Decimal

from django.apps import apps
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from money.models import Transaction

MEALS_SLUG = "meals"
FUEL_SLUG = "fuel"
RENTAL_CAR = "rental_car"

ZERO_MILES = Decimal("0.0")
ZERO_MONEY = Decimal("0.00")

ONE_DP = DecimalField(max_digits=10, decimal_places=1)
TWO_DP = DecimalField(max_digits=20, decimal_places=2)


def build_profitability_context(*, user, tx_qs, mileage_qs, year_hint: int | None = None) -> dict:
    """
    Compute job/invoice profitability from:
      - tx_qs: Transaction queryset (income + expenses)
      - mileage_qs: Miles queryset already filtered to relevant rows
      - year_hint: used to pick mileage rate (defaults to current year)
    Returns a dict suitable for putting into template context.
    """
    MilesModel = apps.get_model("money", "Miles")
    MileageRateModel = apps.get_model("money", "MileageRate")

    # Ensure querysets are the right model types (safety)
    if tx_qs.model is not Transaction:
        raise TypeError("tx_qs must be a Transaction queryset")
    if mileage_qs.model is not MilesModel:
        raise TypeError("mileage_qs must be a Miles queryset")

    inv_year = year_hint or timezone.localdate().year

    rate_obj = (
        MileageRateModel.objects.filter(user=user, year=inv_year).first()
        or MileageRateModel.objects.filter(user__isnull=True, year=inv_year).first()
        or MileageRateModel.objects.filter(user=user).order_by("-year").first()
        or MileageRateModel.objects.filter(user__isnull=True).order_by("-year").first()
    )
    mileage_rate = getattr(rate_obj, "rate", None) or ZERO_MONEY

    mileage_entries = (
        mileage_qs.select_related("client", "event", "vehicle")
        .order_by("date", "pk")
        .annotate(
            miles=Coalesce(F("total"), Value(ZERO_MILES), output_field=ONE_DP),
            amount=ExpressionWrapper(
                Coalesce(F("total"), Value(ZERO_MILES), output_field=ONE_DP) * Value(mileage_rate),
                output_field=TWO_DP,
            ),
        )
    )

    total_mileage_miles = mileage_entries.aggregate(total=Sum("miles")).get("total") or ZERO_MILES
    mileage_dollars = mileage_entries.aggregate(total=Sum("amount")).get("total") or ZERO_MONEY

    def _sum_amount(qs):
        return qs.aggregate(total=Sum("amount")).get("total") or ZERO_MONEY

    income_qs = tx_qs.filter(trans_type=Transaction.INCOME)
    expense_qs = tx_qs.filter(trans_type=Transaction.EXPENSE)

    income_total = _sum_amount(income_qs)
    expense_total = _sum_amount(expense_qs)

    meals_total = ZERO_MONEY
    rental_fuel_total = ZERO_MONEY
    other_expenses_total = ZERO_MONEY

    # iterate expense_qs (already filtered) to bucket for tax logic
    for t in expense_qs:
        sub_slug = (getattr(getattr(t, "sub_cat", None), "slug", "") or "").strip().lower()
        if sub_slug == MEALS_SLUG:
            meals_total += t.amount
        elif sub_slug == FUEL_SLUG and (t.transport_type or "") == RENTAL_CAR:
            rental_fuel_total += t.amount
        else:
            other_expenses_total += t.amount

    net_income = income_total - expense_total

    deductible_meals = meals_total * Decimal("0.50")
    deductible_expenses = other_expenses_total + rental_fuel_total + deductible_meals
    taxable_income = income_total - deductible_expenses - mileage_dollars

    return {
        "tx_list": tx_qs,
        "has_transactions": tx_qs.exists(),

        "income_total": income_total,
        "total_expenses": expense_total,
        "net_income_effective": net_income,

        "deductible_expenses": deductible_expenses,
        "mileage_rate": mileage_rate,
        "total_mileage_miles": total_mileage_miles,
        "mileage_dollars": mileage_dollars,
        "taxable_income": taxable_income,

        "mileage_entries": mileage_entries,
    }
