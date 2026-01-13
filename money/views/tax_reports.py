# _FLIGHTPLAN/money/views/tax_reports.py
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce, ExtractYear
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from equipment.models import Equipment
from money.models import CompanyProfile, Transaction

logger = logging.getLogger(__name__)

TWO_DP = DecimalField(max_digits=20, decimal_places=2)
ZERO = Decimal("0.00")

MEALS_RATE = Decimal("0.50")
PERSONAL_VEHICLE_TRANSPORT = "personal_vehicle"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _selected_year_from_request(request: HttpRequest) -> int | None:
    year_raw = (request.GET.get("year") or "").strip().lower()
    if year_raw in ("", "all", "any"):
        return None
    if year_raw.isdigit():
        return int(year_raw)
    return None


def _year_choices_for_user(user) -> list[int]:
    years = (
        Transaction.objects.filter(user=user)
        .annotate(y=ExtractYear("date"))
        .values_list("y", flat=True)
        .distinct()
        .order_by("-y")
    )
    years = [y for y in years if y is not None]
    if years:
        return years

    current_year = timezone.localdate().year
    return list(range(2023, current_year + 1))[::-1]


def _company_context() -> dict:
    profile = CompanyProfile.get_active()
    return {
        "company_profile": profile,
        "company_name": profile.name_for_display if profile else "",
    }


def _base_amount_expr():
    return Coalesce(F("amount"), Value(ZERO), output_field=TWO_DP)


def _tax_deductible_amount_expr():
    base_amount = _base_amount_expr()
    meals_amount = ExpressionWrapper(base_amount * Value(MEALS_RATE), output_field=TWO_DP)
    return Case(
        When(Q(sub_cat__slug="meals") | Q(sub_cat__slug__iendswith="-meals"), then=meals_amount),
        default=base_amount,
        output_field=TWO_DP,
    )


def _exclude_personal_vehicle_fuel(qs):
    return qs.exclude(
        Q(transport_type=PERSONAL_VEHICLE_TRANSPORT)
        & (Q(sub_cat__slug="fuel") | Q(sub_cat__slug__iendswith="-fuel"))
    )


def _tx_qs_for_user(user, year: int | None):
    qs = (
        Transaction.objects.filter(user=user)
        .select_related("category", "sub_cat", "sub_cat__category", "event", "team")
    )
    if year is not None:
        qs = qs.filter(date__year=year)
    return qs


def _build_tax_statement_context(request: HttpRequest, year: int | None) -> dict:
    qs = _tx_qs_for_user(request.user, year)
    qs = qs.filter(sub_cat__include_in_tax_reports=True)
    qs = _exclude_personal_vehicle_fuel(qs)

    amount_expr = _tax_deductible_amount_expr()

    grouped = (
        qs.values(
            "trans_type",
            "category__category",
            "category__schedule_c_line",
            "sub_cat__sub_cat",
            "sub_cat__slug",
            "sub_cat__schedule_c_line",
        )
        .annotate(total=Coalesce(Sum(amount_expr, output_field=TWO_DP), Value(ZERO), output_field=TWO_DP))
        .order_by("trans_type", "category__category", "sub_cat__sub_cat")
    )

    income_map: dict[str, dict] = defaultdict(lambda: {"cat_total": ZERO, "subs": []})
    expense_map: dict[str, dict] = defaultdict(lambda: {"cat_total": ZERO, "subs": []})

    for row in grouped:
        trans_type = row.get("trans_type") or Transaction.EXPENSE
        cat_name = (row.get("category__category") or "Uncategorized").strip() or "Uncategorized"

        sub_name = (row.get("sub_cat__sub_cat") or "").strip()
        sched_line = (row.get("sub_cat__schedule_c_line") or row.get("category__schedule_c_line") or "").strip()
        amount = (row.get("total") or ZERO).quantize(Decimal("0.01"))

        if trans_type == Transaction.INCOME:
            income_map[cat_name]["cat_total"] = (income_map[cat_name]["cat_total"] + amount).quantize(Decimal("0.01"))
            if sub_name:
                income_map[cat_name]["subs"].append((sub_name, amount, sched_line))
        else:
            expense_map[cat_name]["cat_total"] = (expense_map[cat_name]["cat_total"] + amount).quantize(Decimal("0.01"))
            if sub_name:
                expense_map[cat_name]["subs"].append((sub_name, amount, sched_line))

    income_category_totals = [
        {"category": cat, "total": data["cat_total"], "subcategories": data["subs"]}
        for cat, data in income_map.items()
    ]
    expense_category_totals = [
        {"category": cat, "total": data["cat_total"], "subcategories": data["subs"]}
        for cat, data in expense_map.items()
    ]

    income_category_totals.sort(key=lambda x: x["category"])
    expense_category_totals.sort(key=lambda x: x["category"])

    income_total = sum((r["total"] for r in income_category_totals), start=ZERO).quantize(Decimal("0.01"))
    expense_total = sum((r["total"] for r in expense_category_totals), start=ZERO).quantize(Decimal("0.01"))
    net_profit = (income_total - expense_total).quantize(Decimal("0.01"))

    ctx = {
        "selected_year": year,
        "year_choices": _year_choices_for_user(request.user),
        "income_category_totals": income_category_totals,
        "expense_category_totals": expense_category_totals,
        "income_category_total": income_total,
        "expense_category_total": expense_total,
        "net_profit": net_profit,
        "tax_only": True,
        "now": timezone.now(),
    }
    ctx.update(_company_context())
    return ctx


# -----------------------------------------------------------------------------
# Views (tax-only)
# -----------------------------------------------------------------------------

@login_required
def tax_profit_loss(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)
    ctx = _build_tax_statement_context(request, year)
    ctx["current_page"] = "tax_profit_loss"
    return render(request, "money/taxes/tax_profit_loss.html", ctx)


@login_required
def tax_category_summary(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)
    ctx = _build_tax_statement_context(request, year)
    ctx["current_page"] = "tax_category_summary"
    return render(request, "money/taxes/tax_category_summary.html", ctx)


# -----------------------------------------------------------------------------
# Schedule C
# -----------------------------------------------------------------------------

@login_required
def schedule_c_summary(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)

    qs = _tx_qs_for_user(request.user, year)
    qs = qs.filter(trans_type=Transaction.EXPENSE, sub_cat__include_in_tax_reports=True)
    qs = _exclude_personal_vehicle_fuel(qs)

    deductible_expr = _tax_deductible_amount_expr()
    schedule_c_line = Coalesce(F("sub_cat__schedule_c_line"), F("category__schedule_c_line"), Value(""))

    rows = (
        qs.values("category__category", "sub_cat__sub_cat")
        .annotate(
            schedule_c_line=schedule_c_line,
            total=Coalesce(Sum(deductible_expr, output_field=TWO_DP), Value(ZERO), output_field=TWO_DP),
        )
        .order_by("schedule_c_line", "category__category", "sub_cat__sub_cat")
    )

    by_line = defaultdict(list)
    line_totals = defaultdict(lambda: ZERO)
    grand_total = ZERO

    for r in rows:
        line = (r.get("schedule_c_line") or "").strip() or "Unmapped"
        total = (r.get("total") or ZERO).quantize(Decimal("0.01"))
        by_line[line].append(
            {
                "category": r.get("category__category") or "Uncategorized",
                "sub_cat": r.get("sub_cat__sub_cat") or "",
                "total": total,
            }
        )
        line_totals[line] = (line_totals[line] + total).quantize(Decimal("0.01"))
        grand_total = (grand_total + total).quantize(Decimal("0.01"))

    ctx = {
        "current_page": "schedule_c",
        "selected_year": year,
        "year_choices": _year_choices_for_user(request.user),
        "lines": dict(by_line),
        "line_totals": dict(line_totals),
        "grand_total": grand_total,
        "now": timezone.now(),
    }
    ctx.update(_company_context())
    return render(request, "money/taxes/schedule_c_summary.html", ctx)


# -----------------------------------------------------------------------------
# Form 4797 (Equipment)
# -----------------------------------------------------------------------------

@login_required
def form_4797_view(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)

    equipment_qs = (
        Equipment.objects.filter(user=request.user)
        .select_related("category", "sub_cat")
        .order_by("placed_in_service_date", "id")
    )
    if year is not None:
        equipment_qs = equipment_qs.filter(placed_in_service_date__year=year)

    ctx = {
        "current_page": "form_4797",
        "selected_year": year,
        "year_choices": _year_choices_for_user(request.user),
        "equipment": equipment_qs,
        "now": timezone.now(),
    }
    ctx.update(_company_context())
    return render(request, "money/taxes/form_4797.html", ctx)


@login_required
def form_4797_pdf(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)

    equipment_qs = (
        Equipment.objects.filter(user=request.user)
        .select_related("category", "sub_cat")
        .order_by("placed_in_service_date", "id")
    )
    if year is not None:
        equipment_qs = equipment_qs.filter(placed_in_service_date__year=year)

    ctx = {
        "current_page": "form_4797",
        "selected_year": year,
        "year_choices": _year_choices_for_user(request.user),
        "equipment": equipment_qs,
        "now": timezone.now(),
    }
    ctx.update(_company_context())

    html_string = render_to_string("money/taxes/form_4797_pdf.html", ctx, request=request)
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    suffix = str(year) if year is not None else "ALL"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="Form_4797_{suffix}.pdf"'
    return resp
