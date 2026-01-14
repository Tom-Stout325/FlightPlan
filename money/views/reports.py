# _FLIGHTPLAN/money/views/reports.py
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

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

from money.models import CompanyProfile, InvoiceV2, Transaction

logger = logging.getLogger(__name__)

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
# Financial Statement (non-tax)
# -----------------------------------------------------------------------------

@login_required
def profit_loss(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)
    ctx = _build_statement_context(request, year)
    ctx["current_page"] = "profit_loss"
    return render(request, "money/reports/profit_loss.html", ctx)


@login_required
def profit_loss_pdf(request: HttpRequest, year: int) -> HttpResponse:
    try:
        selected_year = int(year)
    except (TypeError, ValueError):
        selected_year = timezone.localdate().year

    ctx = _build_statement_context(request, selected_year)
    ctx["now"] = timezone.now()

    html = render_to_string("money/reports/financial_statement_pdf.html", ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="financial_statement_{selected_year}.pdf"'
    return resp


@login_required
def category_summary(request: HttpRequest) -> HttpResponse:
    year = _selected_year_from_request(request)
    ctx = _build_statement_context(request, year)
    ctx["current_page"] = "category_summary"
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
# Travel Summary (invoice + transaction rollup)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class _InvoiceRow:
    invoice_number: str
    date: object
    client: str
    amount: Decimal
    status: str
    model: str  # "Invoice" or "InvoiceV2"


def _iter_invoices_for_year(user, year: int):
    for inv in (
        Invoice.objects.filter(client__user=user, date__year=year)
        .select_related("client")
        .only("invoice_number", "date", "amount", "status", "client__business", "client__first", "client__last")
        .order_by("date", "invoice_number")
    ):
        client_name = ""
        if getattr(inv, "client", None):
            business = (inv.client.business or "").strip()
            first = (inv.client.first or "").strip()
            last = (inv.client.last or "").strip()
            client_name = business or " ".join([first, last]).strip()

        yield _InvoiceRow(
            invoice_number=str(inv.invoice_number or ""),
            date=inv.date,
            client=client_name,
            amount=inv.amount or ZERO,
            status=str(getattr(inv, "status", "") or ""),
            model="Invoice",
        )

    for inv in (
        InvoiceV2.objects.filter(user=user, date__year=year)
        .select_related("client")
        .only("invoice_number", "date", "amount", "status", "client__business", "client__first", "client__last")
        .order_by("date", "invoice_number")
    ):
        business = (inv.client.business or "").strip()
        first = (inv.client.first or "").strip()
        last = (inv.client.last or "").strip()
        client_name = business or " ".join([first, last]).strip()

        yield _InvoiceRow(
            invoice_number=str(inv.invoice_number or ""),
            date=inv.date,
            client=client_name,
            amount=inv.amount or ZERO,
            status=str(inv.status or ""),
            model="InvoiceV2",
        )


def build_travel_summary_context(request: HttpRequest) -> dict:
    current_year = timezone.localdate().year
    year = _selected_year_int(request)

    tx_base = Transaction.objects.filter(user=request.user, date__year=year).select_related("sub_cat", "category")
    income_total = (
        tx_base.filter(trans_type=Transaction.INCOME)
        .aggregate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        .get("total")
        or ZERO
    )
    expense_total = (
        tx_base.filter(trans_type=Transaction.EXPENSE)
        .aggregate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=TWO_DP))
        .get("total")
        or ZERO
    )

    invoices = list(_iter_invoices_for_year(request.user, year))
    invoice_total = sum((r.amount for r in invoices), start=ZERO)

    ctx = {
        "current_page": "travel_summary",
        "selected_year": year,
        "year_choices": list(range(2023, current_year + 1)),
        "income_total": income_total,
        "expense_total": expense_total,
        "net_total": income_total - expense_total,
        "invoice_total": invoice_total,
        "invoices": invoices,
    }
    ctx.update(_company_context())
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
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="travel-summary-{ctx["selected_year"]}.pdf"'
    return resp


@login_required
def travel_summary_pdf_download(request: HttpRequest) -> HttpResponse:
    ctx = build_travel_summary_context(request)
    ctx["now"] = timezone.now()
    html = render_to_string("money/reports/travel_summary_pdf.html", ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="travel-summary-{ctx["selected_year"]}.pdf"'
    return resp
