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
from dataclasses import dataclass
from equipment.models import Equipment
from money.models import CompanyProfile, Transaction
from typing import Any

logger = logging.getLogger(__name__)


try:
    from .reports import _brand_pdf_context  
except Exception:  
    _brand_pdf_context = None
    
    
from .reports import ( 
    _selected_year_from_request,
    _year_choices_for_user,
    _company_context,

)






# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
TWO_DP = DecimalField(max_digits=20, decimal_places=2)
MEALS_RATE = Decimal("0.50")
PERSONAL_VEHICLE_TRANSPORT = "personal_vehicle"
ZERO = Decimal("0.00")

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




# =============================================================================
# Profit & Loss (Tax) - Single Year
# =============================================================================

@login_required
def tax_profit_loss(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)

    # Default to the most recent year with data (not the calendar year)
    if year is None:
        choices = _year_choices_for_user(request.user)  # already returns desc years
        year = choices[0] if choices else timezone.localdate().year

    ctx = _build_tax_statement_context(request, year)
    ctx["pl_mode"] = "single"
    ctx["current_page"] = "tax_profit_loss"
    ctx.update(_brand_pdf_context(request))
    ctx["now"] = timezone.now()

    return render(request, "money/taxes/profit_loss_tax.html", ctx)


@login_required
def tax_profit_loss_pdf(request: HttpRequest, year: int) -> HttpResponse:
    try:
        selected_year = int(year)
    except (TypeError, ValueError):
        selected_year = timezone.localdate().year

    ctx = _build_tax_statement_context(request, selected_year)
    ctx["now"] = timezone.now()
    ctx.update(_brand_pdf_context(request))

    html = render_to_string(
        "money/taxes/profit_loss_tax_pdf.html",  # create this PDF template (tax version)
        ctx,
        request=request,
    )

    pdf = HTML(
        string=html,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    preview_flag = (request.GET.get("preview") or "").strip().lower()
    is_preview = preview_flag in {"1", "true", "yes", "y", "on"}

    filename = f"Tax_Profit_Loss_Statement_{selected_year}.pdf"
    disposition = "inline" if is_preview else "attachment"

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return resp


# =============================================================================
# Profit & Loss (Tax) - YOY (3 most recent years)
# =============================================================================

@dataclass(frozen=True)
class YoYSubRow:
    name: str
    schedule_c_line: str
    values: list[Decimal]  # aligned with years


@dataclass(frozen=True)
class YoYCategoryRow:
    category: str
    values: list[Decimal]  # aligned with years
    subrows: list[YoYSubRow]


def _pick_last_three_years(request: HttpRequest, selected_year: int | None) -> list[int]:
    """
    3 most recent years ending at selected_year (or current year).
    Example: 2025 -> [2023, 2024, 2025]
    """
    end = selected_year or timezone.localdate().year
    return [end - 2, end - 1, end]


def _dec(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return ZERO
    try:
        return Decimal(str(v))
    except Exception:
        return ZERO


def _index_statement(
    ctx: dict[str, Any],
    key: str,
) -> tuple[dict[str, Decimal], dict[str, dict[str, tuple[Decimal, str]]]]:
    """
    Builds:
      cat_totals[category] -> total
      subs[category][sub_name] -> (amount, schedule_c_line)

    From ctx["income_category_totals"] or ctx["expense_category_totals"].
    """
    cat_totals: dict[str, Decimal] = {}
    subs: dict[str, dict[str, tuple[Decimal, str]]] = defaultdict(dict)

    for row in ctx.get(key, []):
        cat = (row.get("category") or "Uncategorized").strip() or "Uncategorized"
        cat_totals[cat] = _dec(row.get("total")).quantize(Decimal("0.01"))

        for sub_name, amount, sched in (row.get("subcategories") or []):
            sub = (sub_name or "").strip()
            if not sub:
                continue
            subs[cat][sub] = (_dec(amount).quantize(Decimal("0.01")), (sched or "").strip())

    return cat_totals, subs


def _build_tax_statement_yoy_context(request: HttpRequest, selected_year: int | None = None) -> dict[str, Any]:
    years = _pick_last_three_years(request, selected_year)

    # Build the existing single-year contexts (preserves your totals logic)
    per_year: list[dict[str, Any]] = [_build_tax_statement_context(request, y) for y in years]

    income_cat_maps: list[dict[str, Decimal]] = []
    income_sub_maps: list[dict[str, dict[str, tuple[Decimal, str]]]] = []
    expense_cat_maps: list[dict[str, Decimal]] = []
    expense_sub_maps: list[dict[str, dict[str, tuple[Decimal, str]]]] = []

    for ctx in per_year:
        ic, isubs = _index_statement(ctx, "income_category_totals")
        ec, esubs = _index_statement(ctx, "expense_category_totals")
        income_cat_maps.append(ic)
        income_sub_maps.append(isubs)
        expense_cat_maps.append(ec)
        expense_sub_maps.append(esubs)

    income_categories = sorted(set().union(*[m.keys() for m in income_cat_maps]))
    expense_categories = sorted(set().union(*[m.keys() for m in expense_cat_maps]))

    def build_section(
        categories: list[str],
        cat_maps: list[dict[str, Decimal]],
        sub_maps: list[dict[str, dict[str, tuple[Decimal, str]]]],
    ) -> list[YoYCategoryRow]:
        rows: list[YoYCategoryRow] = []

        for cat in categories:
            cat_vals = [(cat_maps[i].get(cat, ZERO)).quantize(Decimal("0.01")) for i in range(len(years))]

            all_subs: set[str] = set()
            for i in range(len(years)):
                all_subs |= set(sub_maps[i].get(cat, {}).keys())

            subrows: list[YoYSubRow] = []
            for sub in sorted(all_subs):
                vals: list[Decimal] = []
                sched_line = ""
                for i in range(len(years)):
                    amt, sched = sub_maps[i].get(cat, {}).get(sub, (ZERO, ""))
                    vals.append(amt.quantize(Decimal("0.01")))
                    if sched and not sched_line:
                        sched_line = sched
                subrows.append(YoYSubRow(name=sub, schedule_c_line=sched_line, values=vals))

            rows.append(YoYCategoryRow(category=cat, values=cat_vals, subrows=subrows))

        return rows

    income_rows = build_section(income_categories, income_cat_maps, income_sub_maps)
    expense_rows = build_section(expense_categories, expense_cat_maps, expense_sub_maps)

    income_totals = [(_dec(c.get("income_category_total")).quantize(Decimal("0.01"))) for c in per_year]
    expense_totals = [(_dec(c.get("expense_category_total")).quantize(Decimal("0.01"))) for c in per_year]
    net_profits = [(_dec(c.get("net_profit")).quantize(Decimal("0.01"))) for c in per_year]

    ctx: dict[str, Any] = {
        "selected_year": years[-1],
        "years": years,
        "year_choices": _year_choices_for_user(request.user),
        "income_rows": income_rows,
        "expense_rows": expense_rows,
        "income_totals": income_totals,
        "expense_totals": expense_totals,
        "net_profits": net_profits,
        "now": timezone.now(),
    }
    ctx.update(_company_context())

    if "_brand_pdf_context" in globals():
        ctx.update(_brand_pdf_context(request))

    return ctx


@login_required
def tax_profit_loss_yoy(request: HttpRequest) -> HttpResponse:
    try:
        ending_year = int(request.GET.get("year") or 0) or timezone.localdate().year
    except (TypeError, ValueError):
        ending_year = timezone.localdate().year

    ctx = _build_tax_statement_yoy_context(request, ending_year)
    ctx["pl_mode"] = "yoy"
    ctx["current_page"] = "tax_profit_loss"
    return render(request, "money/taxes/profit_loss_tax_yoy.html", ctx)


@login_required
def tax_profit_loss_yoy_pdf(request: HttpRequest) -> HttpResponse:
    """
    PDF for Tax Profit & Loss YOY (3 most recent years).
    ?preview=1 -> inline (new tab)
    otherwise  -> attachment (download)
    Optional: ?year=2025 to set ending year
    """
    try:
        ending_year = int(request.GET.get("year") or 0) or timezone.localdate().year
    except (TypeError, ValueError):
        ending_year = timezone.localdate().year

    ctx = _build_tax_statement_yoy_context(request, ending_year)
    ctx["now"] = timezone.now()

    html = render_to_string(
        "money/taxes/profit_loss_tax_yoy_pdf.html",  # create this PDF template (tax version)
        ctx,
        request=request,
    )

    pdf = HTML(
        string=html,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    preview_flag = (request.GET.get("preview") or "").strip().lower()
    is_preview = preview_flag in {"1", "true", "yes", "y", "on"}

    years = ctx.get("years") or [ending_year - 2, ending_year - 1, ending_year]
    filename = f"Tax_Profit_Loss_YOY_{years[0]}_{years[-1]}.pdf"
    disposition = "inline" if is_preview else "attachment"

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return resp







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
    schedule_c_line_expr = Coalesce(
        F("sub_cat__schedule_c_line"),
        F("category__schedule_c_line"),
        Value(""),
    )

    rows = (
        qs.values(
            "category__category",
            "sub_cat__sub_cat",
            "sub_cat__slug",
        )
        .annotate(
            schedule_c_line=schedule_c_line_expr,
            raw_total=Coalesce(Sum("amount"), Value(ZERO)),
            deductible_total=Coalesce(Sum(deductible_expr), Value(ZERO)),
        )
        .order_by("schedule_c_line", "category__category", "sub_cat__sub_cat")
    )

    by_line = defaultdict(list)
    line_totals = defaultdict(lambda: ZERO)
    grand_total = ZERO

    for r in rows:
        line = (r.get("schedule_c_line") or "").strip() or "Unmapped"

        raw_total = (r.get("raw_total") or ZERO).quantize(Decimal("0.01"))
        deductible_total = (r.get("deductible_total") or ZERO).quantize(Decimal("0.01"))

        by_line[line].append(
            {
                "category": r.get("category__category") or "Uncategorized",
                "sub_cat": r.get("sub_cat__sub_cat") or "",
                "sub_cat_slug": r.get("sub_cat__slug") or "",
                "raw_total": raw_total,
                "deductible_total": deductible_total,
            }
        )

        line_totals[line] = (line_totals[line] + deductible_total).quantize(Decimal("0.01"))
        grand_total = (grand_total + deductible_total).quantize(Decimal("0.01"))

    # Convert dict -> list shaped like the template expects
    def _sort_key(line_key: str):
        # Put numeric lines first, then Unmapped last
        if line_key == "Unmapped":
            return (1, 10**9, line_key)
        try:
            return (0, int(line_key), line_key)
        except ValueError:
            return (0, 10**8, line_key)

    lines = []
    for line_key in sorted(by_line.keys(), key=_sort_key):
        lines.append(
            {
                "line": line_key,
                "category_label": "",  # optional: set a human label if you have one
                "breakdown": by_line[line_key],
                "total": line_totals[line_key],
            }
        )

    ctx = {
        "current_page": "schedule_c",
        "selected_year": year,
        "years": _year_choices_for_user(request.user),  # <-- template expects "years"
        "lines": lines,                                 # <-- template expects list of objects/dicts
        "line_totals": dict(line_totals),
        "grand_total": grand_total,
        "meals_rate": Decimal("0.50"),  # or pull from your helper/settings if you have one
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
