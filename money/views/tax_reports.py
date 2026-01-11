# _FLIGHTPLAN/money/views/tax_reports.py

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
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

def _selected_year_from_request(request) -> int:
    current_year = timezone.localdate().year
    year_raw = (request.GET.get("year") or "").strip()
    return int(year_raw) if year_raw.isdigit() else current_year


def _tx_base_qs(user, year: int | None):
    qs = (
        Transaction.objects.filter(user=user)
        .select_related("category", "sub_cat", "sub_cat__category", "event", "team")
    )
    if year is not None:
        qs = qs.filter(date__year=year)
    return qs


def _tax_deductible_amount_expr():
    base_amount = Coalesce(F("amount"), Value(ZERO), output_field=TWO_DP)
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


def _company_context():
    profile = CompanyProfile.get_active()
    return {
        "company_profile": profile,
        "company_name": profile.name_for_display if profile else "",
    }


def _summary_context(request, year: int, *, tax_only: bool):
    qs = _exclude_personal_vehicle_fuel(_tx_base_qs(request.user, year))

    if tax_only:
        qs = qs.filter(sub_cat__include_in_tax_reports=True)

    deductible_expr = _tax_deductible_amount_expr()

    grouped = (
        qs.values(
            "trans_type",
            "category__category",
            "category__schedule_c_line",
            "sub_cat__sub_cat",
            "sub_cat__slug",
            "sub_cat__schedule_c_line",
        )
        .annotate(
            total=Coalesce(
                Sum(deductible_expr, output_field=TWO_DP),
                Value(ZERO),
                output_field=TWO_DP,
            )
        )
        .order_by("trans_type", "category__category", "sub_cat__sub_cat")
    )

    data = {
        Transaction.INCOME: defaultdict(list),
        Transaction.EXPENSE: defaultdict(list),
    }
    category_totals = {
        Transaction.INCOME: defaultdict(lambda: Decimal("0.00")),
        Transaction.EXPENSE: defaultdict(lambda: Decimal("0.00")),
    }
    trans_totals = {
        Transaction.INCOME: Decimal("0.00"),
        Transaction.EXPENSE: Decimal("0.00"),
    }

    for row in grouped:
        trans_type = row.get("trans_type") or Transaction.EXPENSE
        cat_name = row.get("category__category") or "Uncategorized"
        total = (row.get("total") or Decimal("0.00")).quantize(Decimal("0.01"))

        data[trans_type][cat_name].append(
            {
                "sub_cat": row.get("sub_cat__sub_cat") or "",
                "sub_slug": row.get("sub_cat__slug") or "",
                "total": total,
                "schedule_c_line": (row.get("sub_cat__schedule_c_line") or row.get("category__schedule_c_line") or ""),
            }
        )
        category_totals[trans_type][cat_name] = (category_totals[trans_type][cat_name] + total).quantize(Decimal("0.01"))
        trans_totals[trans_type] = (trans_totals[trans_type] + total).quantize(Decimal("0.01"))

    net = (trans_totals[Transaction.INCOME] - trans_totals[Transaction.EXPENSE]).quantize(Decimal("0.01"))

    ctx = {
        "selected_year": year,
        "year_choices": list(range(2023, timezone.localdate().year + 1)),
        "tax_only": tax_only,
        "groups": data,
        "category_totals": category_totals,
        "totals": trans_totals,
        "net": net,
        "now": timezone.now(),
    }
    ctx.update(_company_context())
    return ctx


# -----------------------------------------------------------------------------
# Views
# -----------------------------------------------------------------------------

@login_required
def financial_statement(request):
    year = _selected_year_from_request(request)
    ctx = _summary_context(request, year, tax_only=False)
    ctx["current_page"] = "financial_statement"
    return render(request, "money/taxes/financial_statement.html", ctx)


@login_required
def tax_financial_statement(request):
    year = _selected_year_from_request(request)
    ctx = _summary_context(request, year, tax_only=True)
    ctx["current_page"] = "tax_financial_statement"
    return render(request, "money/taxes/tax_financial_statement.html", ctx)


@login_required
def tax_category_summary(request):
    year = _selected_year_from_request(request)
    ctx = _summary_context(request, year, tax_only=True)
    ctx["current_page"] = "tax_category_summary"
    return render(request, "money/taxes/tax_category_summary.html", ctx)


@login_required
def category_summary(request):
    year = _selected_year_from_request(request)
    ctx = _summary_context(request, year, tax_only=False)
    ctx["current_page"] = "category_summary"
    return render(request, "money/taxes/category_summary.html", ctx)


@login_required
def financial_statement_pdf(request, year: int):
    try:
        selected_year = int(year)
    except (TypeError, ValueError):
        selected_year = timezone.localdate().year

    ctx = _summary_context(request, selected_year, tax_only=False)
    html_string = render_to_string("money/taxes/financial_statement_pdf.html", ctx, request=request)
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="Financial_Statement_{selected_year}.pdf"'
    return resp


@login_required
def category_summary_pdf(request):
    year = _selected_year_from_request(request)
    ctx = _summary_context(request, year, tax_only=False)
    html_string = render_to_string("money/taxes/category_summary_pdf.html", ctx, request=request)
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="Category_Summary_{year}.pdf"'
    return resp


# -----------------------------------------------------------------------------
# Schedule C
# -----------------------------------------------------------------------------

@login_required
def schedule_c_summary(request):
    year = _selected_year_from_request(request)

    qs = _exclude_personal_vehicle_fuel(_tx_base_qs(request.user, year))
    qs = qs.filter(trans_type=Transaction.EXPENSE, sub_cat__include_in_tax_reports=True)

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
    line_totals = defaultdict(lambda: Decimal("0.00"))
    grand_total = Decimal("0.00")

    for r in rows:
        line = (r.get("schedule_c_line") or "").strip() or "Unmapped"
        total = (r.get("total") or Decimal("0.00")).quantize(Decimal("0.01"))
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
        "year_choices": list(range(2023, timezone.localdate().year + 1)),
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
def form_4797_view(request):
    year = _selected_year_from_request(request)

    equipment_qs = (
        Equipment.objects.filter(user=request.user)
        .select_related("category", "sub_cat")
        .order_by("placed_in_service_date", "id")
    )

    ctx = {
        "current_page": "form_4797",
        "selected_year": year,
        "year_choices": list(range(2023, timezone.localdate().year + 1)),
        "equipment": equipment_qs,
        "now": timezone.now(),
    }
    ctx.update(_company_context())
    return render(request, "money/taxes/form_4797.html", ctx)


@login_required
def form_4797_pdf(request):
    year = _selected_year_from_request(request)

    equipment_qs = (
        Equipment.objects.filter(user=request.user)
        .select_related("category", "sub_cat")
        .order_by("placed_in_service_date", "id")
    )

    ctx = {
        "current_page": "form_4797",
        "selected_year": year,
        "equipment": equipment_qs,
        "now": timezone.now(),
    }
    ctx.update(_company_context())

    html_string = render_to_string("money/taxes/form_4797_pdf.html", ctx, request=request)
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="Form_4797_{year}.pdf"'
    return resp
