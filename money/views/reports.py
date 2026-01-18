# _FLIGHTPLAN/money/views/reports.py
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, ExtractYear
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from weasyprint import HTML

from django.apps import apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView
from typing import Any

from money.services.profitability import build_profitability_context

from money.models import (
        CompanyProfile, 
        InvoiceV2, 
        Transaction,
        Category,
        Event,
)










TWO_DP = DecimalField(max_digits=20, decimal_places=2)
ZERO = Decimal("0.00")


# -----------------------------------------------------------------------------
# Report cards (landing page)
# -----------------------------------------------------------------------------

FINANCIAL_REPORT_CARDS = [
    {
        "key": "profit_loss",
        "title": "Profit & Loss Statement",
        "subtitle": "View income, expenses, and net profit by category.",
        "icon": "fa-solid fa-chart-line",
        "bg_color": "#c6dff4",
        "text_class": "text-primary",
        "url_name": "money:profit_loss",
    },
    {
        "key": "category_summary",
        "title": "Category Summary",
        "subtitle": "Summary of income and expenses by category and sub-category.",
        "icon": "fa-solid fa-list-check",
        "bg_color": "#c6dff4",
        "text_class": "text-primary",
        "url_name": "money:category_summary",
    },
    {
        "key": "travel_summary",
        "title": "Travel Summary",
        "subtitle": "Filter by year; see travel expenses and net income.",
        "icon": "fa-solid fa-receipt",
        "bg_color": "#c6dff4",
        "text_class": "text-primary",
        "url_name": "money:travel_summary",
    },
    {
        "key": "nhra_summary",
        "title": "NHRA Summary",
        "subtitle": "Compare NHRA income and expenses across years.",
        "icon": "fa-solid fa-tag",
        "bg_color": "#c6dff4",
        "text_class": "text-primary",
        "url_name": "money:nhra_summary",
    },
    {
        "key": "nhra_summary_report",
        "title": "Race Expense Report",
        "subtitle": "NHRA travel rollup (income vs race expenses) by year.",
        "icon": "fa-solid fa-flag-checkered",
        "bg_color": "#c6dff4",
        "text_class": "text-primary",
        "url_name": "money:nhra_summary_report",
    },
    {
        "key": "travel_expense_analysis",
        "title": "Travel Expenses",
        "subtitle": "Analyze travel expenses for events.",
        "icon": "fa-solid fa-plane-departure",
        "bg_color": "#c6dff4",
        "text_class": "text-primary",
        "url_name": "money:travel_expense_analysis",
    },
]

TAX_REPORT_CARDS = [
    {
        "key": "form_4797",
        "title": "Form 4797",
        "subtitle": "Report gains from sale of business property and equipment.",
        "icon": "fa-solid fa-cash-register",
        "bg_color": "#caf2e7",
        "text_class": "text-success",
        "url_name": "money:form_4797",
    },
    {
        "key": "schedule_c",
        "title": "Schedule C",
        "subtitle": "Deductible totals using tax flags + Schedule C line mapping.",
        "icon": "fa-solid fa-file-invoice-dollar",
        "bg_color": "#caf2e7",
        "text_class": "text-success",
        "url_name": "money:schedule_c_summary",
    },
    {
        "key": "tax_profit_loss",
        "title": "Taxable Profit & Loss",
        "subtitle": "Tax-adjusted statement (meals %, etc.).",
        "icon": "fa-solid fa-chart-line",
        "bg_color": "#caf2e7",
        "text_class": "text-success",
        "url_name": "money:tax_profit_loss",
    },
    {
        "key": "tax_category_summary",
        "title": "Tax Category Summary",
        "subtitle": "Tax-only categories/subcategories (include-in-tax flag).",
        "icon": "fa-solid fa-list-check",
        "bg_color": "#caf2e7",
        "text_class": "text-success",
        "url_name": "money:tax_category_summary",
    },
]


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------

def _company_context() -> dict:
    profile = CompanyProfile.get_active()
    return {
        "company_profile": profile,
        "company_name": profile.name_for_display if profile else "",
    }


def _enabled_report_keys() -> set[str] | None:
    keys = getattr(settings, "ENABLED_REPORTS", None)
    if not keys:
        return None
    if isinstance(keys, (list, tuple, set)):
        return {str(k) for k in keys}
    return {str(keys)}


def _build_cards(card_defs: list[dict]) -> list[dict]:
    enabled = _enabled_report_keys()

    aliases = {
        "travel_expenses": "travel_expense_analysis",
    }

    built: list[dict] = []
    for c0 in card_defs:
        c = dict(c0)
        key = str(c.get("key") or "").strip()

        if key in aliases:
            key = aliases[key]
            c["key"] = key

        if enabled is not None and key not in enabled:
            continue

        url_name = (c.get("url_name") or c.get("url") or "").strip()

        if url_name.startswith("/") or url_name.startswith("http://") or url_name.startswith("https://"):
            c["url"] = url_name
        else:
            try:
                c["url"] = reverse(url_name) if url_name else "#"
            except NoReverseMatch:
                c["url"] = "#"

        built.append(c)

    return built


def _selected_year_from_request(request: HttpRequest) -> int | None:
    year_raw = (request.GET.get("year") or "").strip().lower()
    if year_raw in ("", "all", "any"):
        return None
    if year_raw.isdigit():
        return int(year_raw)
    return None


def _selected_year_int(request: HttpRequest) -> int:
    current_year = timezone.localdate().year
    year_raw = (request.GET.get("year") or "").strip()
    return int(year_raw) if year_raw.isdigit() else current_year


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


def _tx_qs_for_user(user, year: int | None):
    qs = (Transaction.objects.filter(user=user).select_related("category", "sub_cat", "sub_cat__category", "event", "team"))
    qs = qs.filter(sub_cat__include_in_pl_reports=True)

    if year is not None:
        qs = qs.filter(date__year=year)
    return qs


def _base_amount_expr():
    return Coalesce(F("amount"), Value(ZERO), output_field=TWO_DP)


def _build_statement_context(request: HttpRequest, year: int | None) -> dict:
    qs = _tx_qs_for_user(request.user, year)

    grouped = (
        qs.values(
            "trans_type",
            "category__category",
            "category__schedule_c_line",
            "sub_cat__sub_cat",
            "sub_cat__slug",
            "sub_cat__schedule_c_line",
        )
        .annotate(total=Coalesce(Sum(_base_amount_expr(), output_field=TWO_DP), Value(ZERO), output_field=TWO_DP))
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
        "tax_only": False,
        "now": timezone.now(),
    }
    ctx.update(_company_context())
    return ctx


def _brand_pdf_context(request: HttpRequest) -> dict[str, Any]:
    profile = None
    try:
        profile = CompanyProfile.get_active()
    except Exception:
        profile = None

    return {
        "BRAND_PROFILE": profile,
        "BRAND_LOGO_URL": _absolute_logo_url(request, profile),
    }

# -----------------------------------------------------------------------------
# Reports landing page
# -----------------------------------------------------------------------------

@login_required
def reports_page(request: HttpRequest) -> HttpResponse:
    ctx = {
        "current_page": "reports",
        "financial_cards": _build_cards(FINANCIAL_REPORT_CARDS),
        "tax_cards": _build_cards(TAX_REPORT_CARDS),
        "enabled_reports": getattr(settings, "ENABLED_REPORTS", None),
    }
    ctx.update(_company_context())
    return render(request, "money/reports/reports.html", ctx)


# -----------------------------------------------------------------------------
# Profit and Loss (non-tax)
# -----------------------------------------------------------------------------


@login_required
def profit_loss(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)

    # Default to the most recent year with data (not the calendar year)
    if year is None:
        choices = _year_choices_for_user(request.user)  # already returns desc years
        year = choices[0] if choices else timezone.localdate().year

    ctx = _build_statement_context(request, year)
    ctx["pl_mode"] = "single"
    ctx["current_page"] = "profit_loss"
    ctx.update(_brand_pdf_context(request))

    return render(request, "money/reports/profit_loss.html", ctx)




@login_required
def profit_loss_pdf(request: HttpRequest, year: int) -> HttpResponse:
    try:
        selected_year = int(year)
    except (TypeError, ValueError):
        selected_year = timezone.localdate().year

    # Build report context first
    ctx = _build_statement_context(request, selected_year)
    ctx["now"] = timezone.now()

    # Inject shared brand context (logo + profile)
    ctx.update(_brand_pdf_context(request))

    html = render_to_string(
        "money/reports/profit_loss_pdf.html",
        ctx,
        request=request,
    )

    pdf = HTML(
        string=html,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    preview_flag = (request.GET.get("preview") or "").strip().lower()
    is_preview = preview_flag in {"1", "true", "yes", "y", "on"}

    filename = f"Profit_Loss_Statement_{selected_year}.pdf"
    disposition = "inline" if is_preview else "attachment"

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return resp



# Profit and Loss - YOY

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


def _index_statement(ctx: dict[str, Any], key: str) -> tuple[dict[str, Decimal], dict[str, dict[str, tuple[Decimal, str]]]]:
    """
    Builds:
      cat_totals[category] -> total
      subs[category][sub_name] -> (amount, schedule_c_line)
    From your ctx["income_category_totals"] or ctx["expense_category_totals"] list.
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




def _build_statement_yoy_context(request: HttpRequest, selected_year: int | None = None) -> dict[str, Any]:
    years = _pick_last_three_years(request, selected_year)

    # Build the existing single-year contexts (this preserves your current totals logic)
    per_year: list[dict[str, Any]] = [_build_statement_context(request, y) for y in years]

    # Index each year for quick lookup
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

    # Union of categories across the 3 years
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

            # Union subcategory names for this category across years
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
                    # Prefer latest non-empty schedule line
                    if sched and not sched_line:
                        sched_line = sched
                subrows.append(YoYSubRow(name=sub, schedule_c_line=sched_line, values=vals))

            rows.append(YoYCategoryRow(category=cat, values=cat_vals, subrows=subrows))

        return rows

    income_rows = build_section(income_categories, income_cat_maps, income_sub_maps)
    expense_rows = build_section(expense_categories, expense_cat_maps, expense_sub_maps)

    # Year totals (use the existing totals from each single-year ctx)
    income_totals = [(_dec(c.get("income_category_total")).quantize(Decimal("0.01"))) for c in per_year]
    expense_totals = [(_dec(c.get("expense_category_total")).quantize(Decimal("0.01"))) for c in per_year]
    net_profits = [(_dec(c.get("net_profit")).quantize(Decimal("0.01"))) for c in per_year]

    ctx: dict[str, Any] = {
        "selected_year": years[-1],
        "years": years,
        "year_choices": _year_choices_for_user(request.user),  # still useful if you want a dropdown
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
def profit_loss_yoy(request: HttpRequest) -> HttpResponse:
    try:
        ending_year = int(request.GET.get("year") or 0) or timezone.localdate().year
    except (TypeError, ValueError):
        ending_year = timezone.localdate().year

    ctx = _build_statement_yoy_context(request, ending_year)
    ctx["pl_mode"] = "yoy"
    ctx["current_page"] = "profit_loss"
    return render(request, "money/reports/profit_loss_yoy.html", ctx)




@login_required
def profit_loss_yoy_pdf(request: HttpRequest) -> HttpResponse:
    """
    PDF for Profit & Loss YOY (3 most recent years).
    ?preview=1 -> inline (new tab)
    otherwise  -> attachment (download)
    Optional: ?year=2025 to set ending year
    """
    try:
        ending_year = int(request.GET.get("year") or 0) or timezone.localdate().year
    except (TypeError, ValueError):
        ending_year = timezone.localdate().year

    ctx = _build_statement_yoy_context(request, ending_year)
    ctx["now"] = timezone.now()

    html = render_to_string(
        "money/reports/profit_loss_yoy_pdf.html",
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
    filename = f"Profit_Loss_YOY_{years[0]}_{years[-1]}.pdf"
    disposition = "inline" if is_preview else "attachment"

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return resp




# -----------------------------------------------------------------------------
# Categories & Sub Categories
# -----------------------------------------------------------------------------

@login_required
def category_summary(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)
    ctx = _build_statement_context(request, year)
    ctx["current_page"] = "category_summary"

    ctx["categories"] = (
        Category.objects
        .filter(user=request.user)
        .prefetch_related("subcategories")
        .order_by("category")
    )

    return render(request, "money/reports/category_summary.html", ctx)


@login_required
def category_summary_pdf(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)
    ctx = _build_statement_context(request, year)
    ctx["now"] = timezone.now()

    html = render_to_string("money/reports/category_summary_pdf.html", ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()

    suffix = str(year) if year is not None else "ALL"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="category_summary_{suffix}.pdf"'
    return resp


# -----------------------------------------------------------------------------
# NHRA Summary (simple)
# -----------------------------------------------------------------------------

@login_required
def nhra_summary(request: HttpRequest) -> HttpResponse:
    current_year = timezone.localdate().year
    year = _selected_year_int(request)

    qs = (
        Transaction.objects.filter(user=request.user, date__year=year)
        .select_related("event")
        .only("id", "amount", "trans_type", "event__title")
    )

    by_event: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"income": ZERO, "expense": ZERO})

    for t in qs:
        event_name = (t.event.title if t.event else "Unassigned").strip() or "Unassigned"
        if t.trans_type == Transaction.INCOME:
            by_event[event_name]["income"] += (t.amount or ZERO)
        else:
            by_event[event_name]["expense"] += (t.amount or ZERO)

    summary = []
    for event, totals in by_event.items():
        income = totals["income"]
        expense = totals["expense"]
        summary.append({"event": event, "income": income, "expense": expense, "net": income - expense})

    ctx = {
        "current_page": "nhra_summary",
        "selected_year": year,
        "year_choices": list(range(2023, current_year + 1)),
        "summary": sorted(summary, key=lambda x: x["event"]),
    }
    ctx.update(_company_context())
    return render(request, "money/reports/nhra_summary.html", ctx)


# -----------------------------------------------------------------------------
# Race Expense Report (NHRA Summary Report)
# -----------------------------------------------------------------------------

def _nhra_travel_expense_tokens() -> list[str]:
    tokens = getattr(settings, "NHRA_TRAVEL_EXPENSE_SUBCATEGORY_TOKENS", None)
    if tokens:
        return [str(t).strip() for t in tokens if str(t).strip()]
    return [
        "airfare",
        "car-rental",
        "fuel",
        "hotels",
        "lodging",
        "meals",
        "parking",
        "rideshare",
        "tolls",
    ]


def _slug_token_filter(field: str, tokens: list[str]) -> Q:
    q = Q()
    for t in tokens:
        t = (t or "").strip().lower()
        if not t:
            continue
        q |= Q(**{field: t}) | Q(**{f"{field}__iendswith": f"-{t}"})
    return q


def _nhra_summary_report_context(request: HttpRequest) -> dict:
    current_year = timezone.localdate().year
    year = _selected_year_int(request)
    tokens = _nhra_travel_expense_tokens()

    base = Transaction.objects.filter(user=request.user, date__year=year).select_related("event", "sub_cat")

    income = (
        base.filter(trans_type=Transaction.INCOME)
        .aggregate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        .get("total")
        or ZERO
    )

    expense_q = Q(trans_type=Transaction.EXPENSE) & Q(sub_cat__isnull=False) & _slug_token_filter("sub_cat__slug", tokens)
    expenses = (
        base.filter(expense_q)
        .aggregate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        .get("total")
        or ZERO
    )

    ctx = {
        "current_page": "nhra_summary_report",
        "selected_year": year,
        "year_choices": list(range(2023, current_year + 1)),
        "income_total": income,
        "expense_total": expenses,
        "net_total": income - expenses,
        "tokens": tokens,
    }
    ctx.update(_company_context())
    return ctx


@login_required
def nhra_summary_report(request: HttpRequest) -> HttpResponse:
    return render(request, "money/reports/nhra_summary_report.html", _nhra_summary_report_context(request))


@login_required
def nhra_summary_report_pdf(request: HttpRequest) -> HttpResponse:
    ctx = _nhra_summary_report_context(request)
    ctx["now"] = timezone.now()
    html = render_to_string("money/reports/nhra_summary_report_pdf.html", ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="race-expense-report-{ctx["selected_year"]}.pdf"'
    return resp


# -----------------------------------------------------------------------------
# Travel Expense Analysis (event receipts-focused)
# -----------------------------------------------------------------------------

def _travel_income_selector() -> Q:
    slugs = getattr(settings, "TRAVEL_INCOME_SUBCATEGORY_SLUGS", None) or []
    slugs = [str(s).strip().lower() for s in slugs if str(s).strip()]
    if not slugs:
        slugs = ["services-drone", "services-drone-photo-video", "services-drone-video"]
    return Q(trans_type=Transaction.INCOME) & _slug_token_filter("sub_cat__slug", slugs)


def _travel_expense_selector_q() -> Q:
    slugs = getattr(settings, "TRAVEL_EXPENSE_SUBCATEGORY_SLUGS", None) or []
    slugs = [str(s).strip().lower() for s in slugs if str(s).strip()]
    if not slugs:
        slugs = _nhra_travel_expense_tokens()
    return Q(trans_type=Transaction.EXPENSE) & _slug_token_filter("sub_cat__slug", slugs)


def _travel_expense_context(request: HttpRequest) -> dict:
    current_year = timezone.localdate().year
    year = _selected_year_int(request)

    base = Transaction.objects.filter(user=request.user, date__year=year).select_related("sub_cat", "event")

    income_total = (
        base.filter(_travel_income_selector())
        .aggregate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        .get("total")
        or ZERO
    )

    expense_q = _travel_expense_selector_q()
    expense_total = (
        base.filter(expense_q)
        .aggregate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        .get("total")
        or ZERO
    )

    breakdown_qs = (
        base.filter(expense_q)
        .values("sub_cat__sub_cat", "sub_cat__slug")
        .annotate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        .order_by("-total")
    )

    breakdown = []
    total_for_pct = expense_total if expense_total else ZERO
    for row in breakdown_qs:
        total = row["total"] or ZERO
        pct = (total / total_for_pct * Decimal("100.0")) if total_for_pct else ZERO
        breakdown.append(
            {
                "name": row["sub_cat__sub_cat"] or row["sub_cat__slug"] or "Unassigned",
                "slug": row["sub_cat__slug"] or "",
                "total": total,
                "pct": pct,
            }
        )

    ctx = {
        "current_page": "travel_expense_analysis",
        "selected_year": year,
        "year_choices": list(range(2023, current_year + 1)),
        "income_total": income_total,
        "expense_total": expense_total,
        "net_total": income_total - expense_total,
        "breakdown": breakdown,
    }
    ctx.update(_company_context())
    return ctx


@login_required
def travel_expense_analysis(request: HttpRequest) -> HttpResponse:
    return render(request, "money/reports/travel_expense_analysis.html", _travel_expense_context(request))


@login_required
def travel_expense_analysis_pdf(request: HttpRequest) -> HttpResponse:
    ctx = _travel_expense_context(request)
    ctx["now"] = timezone.now()
    html = render_to_string("money/reports/travel_expense_analysis_pdf.html", ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="travel-expense-analysis-{ctx["selected_year"]}.pdf"'
    return resp





# -----------------------------------------------------------------------------
# Travel Summary (InvoiceV2 + primary travel expense rollup by invoice_number)
# -----------------------------------------------------------------------------
def _absolute_logo_url(request: HttpRequest, profile: CompanyProfile | None) -> str | None:
    if not profile:
        return None
    logo = getattr(profile, "logo", None)
    if not logo:
        return None
    try:
        return request.build_absolute_uri(logo.url)
    except Exception:
        return None

ZERO = Decimal("0.00")
TWO_DP = DecimalField(max_digits=12, decimal_places=2)

# Primary travel buckets only
TRAVEL_SLUGS = ("airfare", "hotels", "car-rental", "fuel")


@dataclass(frozen=True)
class TravelRow:
    invoice: InvoiceV2
    invoice_amount: Decimal
    airfare: Decimal
    hotels: Decimal
    car_rental: Decimal
    fuel: Decimal
    total_expense: Decimal
    net_amount: Decimal


def _avg(total: Decimal, n: int) -> Decimal:
    return (total / n) if n else ZERO


def build_travel_summary_context(request: HttpRequest) -> dict[str, Any]:
    current_year = timezone.localdate().year
    year = _selected_year_int(request)

    invoices = (
        InvoiceV2.objects.filter(user=request.user, date__year=year)
        .select_related("event")
        .only("id", "invoice_number", "date", "amount", "event__title", "event_name")
        .order_by("date", "invoice_number")
    )

    invoice_numbers = [i.invoice_number for i in invoices if i.invoice_number]
    invoice_set = set(invoice_numbers)

    # ---------------------------------
    # Aggregate expenses by invoice + slug
    # ---------------------------------
    expense_map: dict[str, dict[str, Decimal]] = {}

    if invoice_set:
        qs = (
            Transaction.objects.filter(
                user=request.user,
                trans_type=Transaction.EXPENSE,
                date__year=year,
                invoice_number__in=invoice_set,
                sub_cat__slug__in=TRAVEL_SLUGS,
            )
            .values("invoice_number", "sub_cat__slug")
            .annotate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        )

        for row in qs:
            inv_no = row["invoice_number"]
            slug = row["sub_cat__slug"]
            total = row["total"] or ZERO
            expense_map.setdefault(inv_no, {})[slug] = total

    rows: list[TravelRow] = []

    totals = {
        "invoice_amount": ZERO,
        "airfare": ZERO,
        "hotels": ZERO,
        "car_rental": ZERO,
        "fuel": ZERO,
        "total_expense": ZERO,
        "net_amount": ZERO,
    }

    # ---------------------------------
    # Build rows + totals
    # ---------------------------------
    for inv in invoices:
        inv_no = inv.invoice_number or ""
        buckets = expense_map.get(inv_no, {})

        airfare = buckets.get("airfare", ZERO)
        hotels = buckets.get("hotels", ZERO)
        car_rental = buckets.get("car-rental", ZERO)
        fuel = buckets.get("fuel", ZERO)

        total_expense = airfare + hotels + car_rental + fuel
        invoice_amount = inv.amount or ZERO
        net_amount = invoice_amount - total_expense

        rows.append(
            TravelRow(
                invoice=inv,
                invoice_amount=invoice_amount,
                airfare=airfare,
                hotels=hotels,
                car_rental=car_rental,
                fuel=fuel,
                total_expense=total_expense,
                net_amount=net_amount,
            )
        )

        totals["invoice_amount"] += invoice_amount
        totals["airfare"] += airfare
        totals["hotels"] += hotels
        totals["car_rental"] += car_rental
        totals["fuel"] += fuel
        totals["total_expense"] += total_expense
        totals["net_amount"] += net_amount

    # ---------------------------------
    # Averages
    # ---------------------------------
    total_invoices = len(rows)
    expense_n = sum(1 for r in rows if r.total_expense > ZERO)

    averages = {
        "invoice_amount": _avg(totals["invoice_amount"], total_invoices),
        "total_expense": _avg(totals["total_expense"], expense_n),
        "net_amount": _avg(totals["net_amount"], total_invoices),
        "airfare": _avg(totals["airfare"], sum(1 for r in rows if r.airfare > ZERO)),
        "hotels": _avg(totals["hotels"], sum(1 for r in rows if r.hotels > ZERO)),
        "car_rental": _avg(totals["car_rental"], sum(1 for r in rows if r.car_rental > ZERO)),
        "fuel": _avg(totals["fuel"], sum(1 for r in rows if r.fuel > ZERO)),
    }

    # ---------------------------------
    # Context
    # ---------------------------------
    ctx: dict[str, Any] = {
        "current_page": "travel_summary",
        "selected_year": year,
        "years": list(range(2023, current_year + 1)),
        "rows": rows,
        "totals": totals,
        "averages": averages,
    }

    ctx.update(_company_context())

    profile = None
    try:
        profile = CompanyProfile.get_active()
    except Exception:
        profile = None

    ctx["BRAND_PROFILE"] = profile
    ctx["BRAND_LOGO_URL"] = _absolute_logo_url(request, profile)

    return ctx



@login_required
def travel_summary(request: HttpRequest) -> HttpResponse:
    return render(request, "money/reports/travel_summary.html", build_travel_summary_context(request))


@login_required
def travel_summary_pdf_preview(request: HttpRequest) -> HttpResponse:
    ctx = build_travel_summary_context(request)
    ctx["now"] = timezone.now()
    html = render_to_string("money/reports/travel_summary_pdf.html", ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    return HttpResponse(pdf, content_type="application/pdf")


@login_required
def travel_summary_pdf_download(request: HttpRequest) -> HttpResponse:
    ctx = build_travel_summary_context(request)
    ctx["now"] = timezone.now()
    html = render_to_string("money/reports/travel_summary_pdf.html", ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    return HttpResponse(
        pdf,
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="travel-summary-{ctx["selected_year"]}.pdf"'},
    )
    
    
    
    



def _get_active_profile() -> CompanyProfile | None:
    try:
        return CompanyProfile.get_active()
    except Exception:
        return None
    
    
def _require_event_owned_by_user(request, pk: int) -> Event:
    # Use your existing ownership helper pattern if you have one
    return Event.objects.get(pk=pk, user=request.user)


class JobReviewView(LoginRequiredMixin, DetailView):
    """
    "Job Review" = profitability hub for an Event (displayed as Job in UI).
    """
    model = Event
    template_name = "money/reports/job_review.html"
    context_object_name = "job"

    def get_object(self, queryset=None):
        return _require_event_owned_by_user(self.request, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        job: Event = ctx["job"]
        user = self.request.user

        # Invoices for this job
        invoices_qs = (
            InvoiceV2.objects.filter(user=user, event=job)
            .select_related("client", "event", "service")
            .order_by("-date", "-pk")
        )

        invoice_numbers = list(
            invoices_qs.exclude(invoice_number__isnull=True).exclude(invoice_number="").values_list("invoice_number", flat=True)
        )

        # Transactions linked to the job OR linked to any invoice_number under the job
        tx_qs = (
            Transaction.objects.filter(user=user)
            .filter(Q(event=job) | Q(invoice_number__in=invoice_numbers))
            .select_related("category", "sub_cat", "sub_cat__category", "event")
            .order_by("date", "pk")
            .distinct()
        )

        # Mileage: prefer Miles.event == job; also include invoice-number-linked miles
        MilesModel = apps.get_model("money", "Miles")

        mileage_qs = MilesModel.objects.filter(user=user).filter(
            Q(event=job) | Q(invoice_number__in=invoice_numbers)
        )

        # Profitability context
        profit_ctx = build_profitability_context(
            user=user,
            tx_qs=tx_qs,
            mileage_qs=mileage_qs,
            year_hint=job.event_year,
        )
        ctx.update(profit_ctx)

        # Revenue: show both "invoiced" and "income tx"
        invoiced_revenue = invoices_qs.aggregate(total=Sum("amount")).get("total") or 0
        ctx["invoices"] = invoices_qs
        ctx["invoiced_revenue"] = invoiced_revenue



        income_total = ctx.get("income_total")  # Decimal
        net_profit = ctx.get("net_income_effective")  # Decimal

        margin_pct = None
        badge_class = "bg-secondary"

        try:
            if income_total and income_total != Decimal("0.00"):
                margin_pct = (net_profit / income_total) * Decimal("100")
                # Color rules
                if margin_pct >= Decimal("50"):
                    badge_class = "bg-success"
                elif margin_pct >= Decimal("20"):
                    badge_class = "bg-warning text-dark"
                else:
                    badge_class = "bg-danger"
        except (InvalidOperation, ZeroDivisionError, TypeError):
            margin_pct = None
            badge_class = "bg-secondary"

        ctx["margin_pct"] = margin_pct
        ctx["margin_badge_class"] = badge_class

        # Brand/profile (you already use this)
        ctx["profile"] = _get_active_profile()

        return ctx
