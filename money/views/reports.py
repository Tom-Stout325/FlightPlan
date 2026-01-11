# _FLIGHTPLAN/money/views/reports.py

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from money.models import CompanyProfile, Invoice, InvoiceV2, Transaction

logger = logging.getLogger(__name__)

TWO_DP = DecimalField(max_digits=20, decimal_places=2)
ZERO = Decimal("0.00")


# -----------------------------------------------------------------------------
# Report cards (landing page)
# -----------------------------------------------------------------------------

FINANCIAL_REPORT_CARDS = [
    {
        "key": "financial_statement",
        "title": "Financial Statement",
        "subtitle": "View income, expenses, and net profit by category.",
        "icon": "fa-solid fa-chart-line",
        "bg_color": "#c6dff4",
        "text_class": "text-primary",
        "url_name": "money:financial_statement",
    },
    {
        # FIXED: was "" in older file, which breaks ENABLED_REPORTS filtering
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
        # NOTE: historically some code used "travel_expenses"
        # but your settings include travel_expense_analysis, so we align to that.
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
        "key": "tax_financial_statement",
        "title": "Tax Financial Statement",
        "subtitle": "Tax-adjusted statement (meals %, etc.).",
        "icon": "fa-solid fa-chart-line",
        "bg_color": "#caf2e7",
        "text_class": "text-success",
        "url_name": "money:tax_financial_statement",
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


def _selected_year(request: HttpRequest) -> int:
    current_year = timezone.localdate().year
    year_raw = (request.GET.get("year") or "").strip()
    return int(year_raw) if year_raw.isdigit() else current_year


# Backwards-compatible alias used by older templates/snippets.
def get_selected_year(request: HttpRequest) -> int:
    return _selected_year(request)


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
    """
    Build card list for landing page, respecting settings.ENABLED_REPORTS.

    Supports a small alias map so cards don't disappear when older keys drift.
    """
    enabled = _enabled_report_keys()

    aliases = {
        "travel_expenses": "travel_expense_analysis",
    }

    built: list[dict] = []
    for c in card_defs:
        c = dict(c)  # shallow copy
        key = str(c.get("key") or "").strip()
        if key in aliases:
            key = aliases[key]
            c["key"] = key

        if enabled is not None and key not in enabled:
            continue

        built.append(c)
    return built


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
# NHRA Summary (simple)
# -----------------------------------------------------------------------------

@login_required
def nhra_summary(request: HttpRequest) -> HttpResponse:
    """Quick NHRA rollup by year and event (Event.title)."""
    current_year = timezone.localdate().year
    year = _selected_year(request)

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
    """
    Build an OR Q() for slug tokens that match:
    - exact: token
    - suffix: *-token (SubCategory.slug is often <category>-<sub_cat>)
    """
    q = Q()
    for t in tokens:
        t = (t or "").strip().lower()
        if not t:
            continue
        q |= Q(**{field: t}) | Q(**{f"{field}__iendswith": f"-{t}"})
    return q


def _nhra_summary_report_context(request: HttpRequest) -> dict:
    current_year = timezone.localdate().year
    year = _selected_year(request)
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
    """
    Income selector for the travel expense analysis:
    - configurable via settings.TRAVEL_INCOME_SUBCATEGORY_SLUGS (list[str])
    """
    slugs = getattr(settings, "TRAVEL_INCOME_SUBCATEGORY_SLUGS", None) or []
    slugs = [str(s).strip().lower() for s in slugs if str(s).strip()]
    if not slugs:
        slugs = ["services-drone", "services-drone-photo-video", "services-drone-video"]
    return Q(trans_type=Transaction.INCOME) & _slug_token_filter("sub_cat__slug", slugs)


def _travel_expense_selector_q() -> Q:
    """
    Expense selector for the travel expense analysis:
    - configurable via settings.TRAVEL_EXPENSE_SUBCATEGORY_SLUGS (list[str])
    """
    slugs = getattr(settings, "TRAVEL_EXPENSE_SUBCATEGORY_SLUGS", None) or []
    slugs = [str(s).strip().lower() for s in slugs if str(s).strip()]
    if not slugs:
        slugs = _nhra_travel_expense_tokens()
    return Q(trans_type=Transaction.EXPENSE) & _slug_token_filter("sub_cat__slug", slugs)


def _travel_expense_context(request: HttpRequest) -> dict:
    current_year = timezone.localdate().year
    year = _selected_year(request)

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
    """Yield both legacy Invoice and InvoiceV2 rows for a given year."""
    for inv in (
        Invoice.objects.filter(user=user, date__year=year)
        .select_related("client")
        .only(
            "invoice_number",
            "date",
            "amount",
            "status",
            "client__business_name",
            "client__first_name",
            "client__last_name",
        )
        .order_by("date", "invoice_number")
    ):
        client_name = ""
        if getattr(inv, "client", None):
            client_name = inv.client.business_name or f"{inv.client.first_name} {inv.client.last_name}".strip()
        yield _InvoiceRow(
            invoice_number=str(inv.invoice_number),
            date=inv.date,
            client=client_name,
            amount=inv.amount or ZERO,
            status=str(getattr(inv, "status", "") or ""),
            model="Invoice",
        )

    for inv in (
        InvoiceV2.objects.filter(user=user, invoice_date__year=year)
        .select_related("client")
        .only(
            "invoice_number",
            "invoice_date",
            "amount",
            "status",
            "client__business_name",
            "client__first_name",
            "client__last_name",
        )
        .order_by("invoice_date", "invoice_number")
    ):
        client_name = ""
        if getattr(inv, "client", None):
            client_name = inv.client.business_name or f"{inv.client.first_name} {inv.client.last_name}".strip()
        yield _InvoiceRow(
            invoice_number=str(inv.invoice_number),
            date=inv.invoice_date,
            client=client_name,
            amount=inv.amount or ZERO,
            status=str(getattr(inv, "status", "") or ""),
            model="InvoiceV2",
        )


def build_travel_summary_context(request: HttpRequest) -> dict:
    current_year = timezone.localdate().year
    year = _selected_year(request)

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
