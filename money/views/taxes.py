import logging

logger = logging.getLogger(__name__)

import csv
import tempfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.conf.urls.static import static
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import (
    Case,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from equipment.models import Equipment
from weasyprint import CSS, HTML

from money.models import Transaction

from ..forms.taxes.taxes import (
    CategoryForm,
    MileageForm,
    MileageRateForm,
    SubCategoryForm,
)
from ..models import (
    Category,
    Miles,
    MileageRate,
    SubCategory,
    Vehicle,
    VehicleYear,
)


def get_selected_year(request):
    year_param = request.GET.get("year")
    current_year = timezone.localdate().year
    return int(year_param) if year_param and year_param.isdigit() else current_year



@login_required
def tax_financial_statement(request):
    year = request.GET.get("year", str(timezone.now().year))
    context = get_summary_data(request, year, tax_only=True)
    context["current_page"] = "reports"
    context["tax_only"] = True
    return render(request, "money/taxes/financial_statement.html", context)


@login_required
def tax_category_summary(request):
    year = request.GET.get("year")
    context = get_summary_data(request, year, tax_only=True)
    context["available_years"] = [
        d.year for d in Transaction.objects.filter(user=request.user)
        .dates("date", "year", order="DESC").distinct()
    ]
    context["current_page"] = "reports"
    context["tax_only"] = True
    return render(request, "money/taxes/category_summary.html", context)




# =============================================================================
# CATEGORIES
# =============================================================================

class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "money/taxes/category_page.html"
    context_object_name = "category"

    def get_queryset(self):
        return Category.objects.prefetch_related("subcategories").order_by("category")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "money/taxes/category_form.html"
    # FIX: your old success_url was 'money:money/category_page' (typo)
    success_url = reverse_lazy("money:category_page")

    def form_valid(self, form):
        messages.success(self.request, "Category added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "money/taxes/category_form.html"
    success_url = reverse_lazy("money:category_page")

    def form_valid(self, form):
        messages.success(self.request, "Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = "money/taxes/category_confirm_delete.html"
    success_url = reverse_lazy("money:category_page")

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Category deleted successfully!")
            return response
        except ProtectedError:
            messages.error(self.request, "Cannot delete category due to related transactions.")
            return redirect("money:category_page")
        except Exception as e:
            logger.error(f"Error deleting category for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting category.")
            return redirect("money:category_page")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


# =============================================================================
# SUBCATEGORIES
# =============================================================================

class SubCategoryCreateView(LoginRequiredMixin, CreateView):
    model = SubCategory
    form_class = SubCategoryForm
    template_name = "money/taxes/sub_category_form.html"
    # FIX: your old url name used slashes in reverse_lazy; should be namespaced
    success_url = reverse_lazy("money:category_page")

    def form_valid(self, form):
        messages.success(self.request, "Sub-Category added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


class SubCategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = SubCategory
    form_class = SubCategoryForm
    template_name = "money/taxes/sub_category_form.html"
    success_url = reverse_lazy("money:category_page")
    context_object_name = "sub_cat"

    def form_valid(self, form):
        messages.success(self.request, "Sub-Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


class SubCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = SubCategory
    template_name = "money/taxes/sub_category_confirm_delete.html"
    success_url = reverse_lazy("money:category_page")

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Sub-Category deleted successfully!")
            return response
        except ProtectedError:
            messages.error(self.request, "Cannot delete sub-category due to related transactions.")
            return redirect("money:category_page")
        except Exception as e:
            logger.error(f"Error deleting sub-category for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting sub-category.")
            return redirect("money:category_page")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


# =============================================================================
# REPORTS (FINANCIAL vs TAX-FILTERED)
# =============================================================================



def get_summary_data(request, year, tax_only: bool = False):
    current_year = timezone.localdate().year

    year_raw = str(year or "").strip().lower()
    all_years = year_raw in {"all", "all years", "all_years"}

    if not year_raw:
        selected_year = current_year
    elif year_raw.isdigit():
        selected_year = int(year_raw)
    elif all_years:
        selected_year = "All"
    else:
        selected_year = current_year


    transactions = (
        Transaction.objects
        .filter(user=request.user)
        .select_related("category", "sub_cat", "sub_cat__category")
    )

    if selected_year != "All":
        transactions = transactions.filter(date__year=selected_year)

    if tax_only:
        # Only include rows where sub_cat exists AND is marked tax-includable
        transactions = transactions.filter(sub_cat__include_in_tax_reports=True)

    income_data = defaultdict(lambda: {
        "total": Decimal("0.00"),
        "subcategories": defaultdict(lambda: [Decimal("0.00"), None]),
    })
    expense_data = defaultdict(lambda: {
        "total": Decimal("0.00"),
        "subcategories": defaultdict(lambda: [Decimal("0.00"), None]),
    })

    for t in transactions:
        # Prefer the transaction.category (it is required) and fall back if needed
        category_obj = t.category or (t.sub_cat.category if t.sub_cat and t.sub_cat.category else None)

        cat_name = getattr(category_obj, "category", None) or "Uncategorized"
        sched_line = getattr(category_obj, "schedule_c_line", None)

        sub_cat_name = t.sub_cat.sub_cat if t.sub_cat else "Uncategorized"

        is_meals = bool(t.sub_cat and (t.sub_cat.slug or "").strip().lower() == "meals")
        is_fuel = bool(t.sub_cat and (t.sub_cat.slug or "").strip().lower() == "fuel")
        is_personal_vehicle = t.transport_type == "personal_vehicle"

        if is_meals:
            amount = (t.amount or Decimal("0.00")) * Decimal("0.5")
        elif is_fuel and is_personal_vehicle:
            amount = Decimal("0.00")
        else:
            amount = t.amount or Decimal("0.00")

        target = income_data if t.trans_type == Transaction.INCOME else expense_data

        target[cat_name]["total"] += amount
        target[cat_name]["subcategories"][sub_cat_name][0] += amount
        target[cat_name]["subcategories"][sub_cat_name][1] = sched_line

    def format_data(data_dict):
        return [
            {
                "category": cat,
                "total": values["total"],
                "subcategories": [
                    (sub, amt_sched[0], amt_sched[1])
                    for sub, amt_sched in values["subcategories"].items()
                ],
            }
            for cat, values in sorted(data_dict.items())
        ]

    income_category_totals = format_data(income_data)
    expense_category_totals = format_data(expense_data)

    income_total = sum(item["total"] for item in income_category_totals)
    expense_total = sum(item["total"] for item in expense_category_totals)
    net_profit = income_total - expense_total

    available_years = (
        Transaction.objects
        .filter(user=request.user)
        .dates("date", "year", order="DESC")
    )

    return {
        "selected_year": selected_year,  # int year OR "All"
        "income_category_totals": income_category_totals,
        "expense_category_totals": expense_category_totals,
        "income_category_total": income_total,
        "expense_category_total": expense_total,
        "net_profit": net_profit,
        "available_years": [d.year for d in available_years],
        "tax_only": tax_only,
    }






@login_required
def tax_category_summary(request):
    year = request.GET.get("year")
    context = get_summary_data(request, year, tax_only=True)
    context["current_page"] = "reports"
    return render(request, "money/taxes/category_summary.html", context)



@login_required
def category_summary(request):
    selected_year = get_selected_year(request)

    # Category Summary is a "financial report" (show everything)
    context = get_summary_data(request, selected_year, tax_only=False)

    # years for the dropdown
    years_qs = (
        Transaction.objects
        .filter(user=request.user)
        .dates("date", "year", order="DESC")
        .distinct()
    )
    context["available_years"] = [d.year for d in years_qs]

    # optional: ensure current year appears even if no txns yet
    current_year = timezone.localdate().year
    if current_year not in context["available_years"]:
        context["available_years"] = [current_year] + context["available_years"]

    context["selected_year"] = selected_year
    context["current_page"] = "reports"
    return render(request, "money/taxes/category_summary.html", context)





@login_required
def category_summary_pdf(request):
    year = request.GET.get("year")
    # Category Summary PDF is a "financial report" (show everything)
    context = get_summary_data(request, year, tax_only=False)
    context["now"] = timezone.now()
    context["selected_year"] = year or timezone.now().year
    context["logo_url"] = request.build_absolute_uri("/static/img/logo.png")

    try:
        template = get_template("money/taxes/category_summary_pdf.html")
        html_string = template.render(context)
        html_string = "<style>@page { size: 8.5in 11in; margin: 1in; }</style>" + html_string

        if request.GET.get("preview") == "1":
            return HttpResponse(html_string)

        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(tmp.name)
            tmp.seek(0)
            response = HttpResponse(tmp.read(), content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="category_summary.pdf"'
            return response
    except Exception as e:
        logger.error(f"Error generating category summary PDF: {e}")
        messages.error(request, "Error generating PDF.")
        return redirect("money:category_summary")


@login_required
def financial_statement(request):
    year = request.GET.get("year", str(timezone.now().year))
    # Financial Statement is a "financial report" (show everything)
    context = get_summary_data(request, year, tax_only=False)
    context["current_page"] = "reports"
    return render(request, "money/taxes/financial_statement.html", context)


@login_required
def financial_statement_pdf(request, year):
    try:
        selected_year = int(year)
    except ValueError:
        selected_year = timezone.now().year

    # Financial Statement PDF is a "financial report" (show everything)
    context = get_summary_data(request, selected_year, tax_only=False)
    context["now"] = timezone.now()

    html_string = render_to_string("money/taxes/financial_statement_pdf.html", context)
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Financial_Statement_{selected_year}.pdf"'
    return response


# =============================================================================
# Schedule C (legacy / slated for removal)
# =============================================================================

def get_schedule_c_summary(transactions):
    """
    NOTE: Legacy. Kept as-is, but now respects include_in_tax_reports if you pass a
    pre-filtered queryset.
    """
    line_summary = defaultdict(lambda: {"total": Decimal("0.00"), "items": set()})

    for t in transactions:
        if not t.sub_cat or not t.sub_cat.category or not t.sub_cat.category.schedule_c_line:
            continue

        line = t.sub_cat.category.schedule_c_line
        amount = t.amount or Decimal("0.00")

        if t.trans_type == Transaction.EXPENSE:
            if t.sub_cat_id == 26:
                amount *= Decimal("0.5")
            elif t.sub_cat_id == 27 and t.transport_type == "personal_vehicle":
                continue
            amount = -abs(amount)

        line_summary[line]["total"] += amount
        line_summary[line]["items"].add(t.sub_cat.category.category)

    return [
        {"line": line, "total": data["total"], "categories": sorted(data["items"])}
        for line, data in sorted(line_summary.items())
    ]


@login_required
def schedule_c_summary(request):
    year = request.GET.get("year", timezone.now().year)

    transactions = (
        Transaction.objects.filter(user=request.user, date__year=year)
        .select_related("sub_cat", "sub_cat__category")
        # ✅ For Schedule C outputs, this should be tax-filtered
        .filter(sub_cat__include_in_tax_reports=True)
    )

    summary = get_schedule_c_summary(transactions)

    income_total = sum(t.amount for t in transactions if t.trans_type == Transaction.INCOME)
    total_expenses = sum(row["total"] for row in summary if row["total"] < 0)
    net_profit = income_total + total_expenses

    return render(
        request,
        "money/taxes/schedule_c_summary.html",
        {
            "summary": summary,
            "income_total": income_total,
            "net_profit": net_profit,
            "selected_year": year,
            "current_page": "reports",
        },
    )


@login_required
def schedule_c_summary_pdf(request, year):
    transactions = (
        Transaction.objects.filter(user=request.user, date__year=year)
        .select_related("sub_cat", "sub_cat__category")
        # ✅ For Schedule C outputs, this should be tax-filtered
        .filter(sub_cat__include_in_tax_reports=True)
    )

    summary = get_schedule_c_summary(transactions)
    income_total = sum(t.amount for t in transactions if t.trans_type == Transaction.INCOME)
    total_expenses = sum(row["total"] for row in summary if row["total"] < 0)
    net_profit = income_total + total_expenses

    logo_url = request.build_absolute_uri(static("images/logo2.png"))

    html = render_to_string(
        "money/taxes/schedule_c_summary_pdf.html",
        {
            "summary": summary,
            "income_total": income_total,
            "net_profit": net_profit,
            "selected_year": year,
            "logo_url": logo_url,
        },
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="schedule_c_summary_{year}.pdf"'
    HTML(string=html).write_pdf(response)
    return response


# =============================================================================
# FORM 4797 (equipment sales)
# =============================================================================

@login_required
def form_4797_view(request):
    sold_equipment = Equipment.objects.filter(date_sold__isnull=False, sale_price__isnull=False)
    report_data = []

    for item in sold_equipment:
        purchase_cost = Decimal("0.00") if item.deducted_full_cost else (item.purchase_price or Decimal("0.00"))
        gain = (item.sale_price or Decimal("0.00")) - (item.purchase_cost or Decimal("0.00"))

        report_data.append(
            {
                "name": item.name,
                "date_sold": item.date_sold,
                "sale_price": item.sale_price,
                "purchase_cost": item.purchase_cost,
                "gain": gain,
            }
        )

    context = {
        "report_data": report_data,
        "current_page": "form_4797",
    }
    return render(request, "money/taxes/form_4797.html", context)


@login_required
def form_4797_pdf(request):
    sold_equipment = Equipment.objects.filter(date_sold__isnull=False, sale_price__isnull=False)
    report_data = []

    for item in sold_equipment:
        basis = Decimal("0.00") if item.deducted_full_cost else (item.purchase_price or Decimal("0.00"))
        gain = (item.sale_price or Decimal("0.00")) - basis

        report_data.append(
            {
                "name": item.name,
                "date_sold": item.date_sold,
                "sale_price": item.sale_price,
                "basis": basis,
                "gain": gain,
            }
        )

    context = {
        "report_data": report_data,
        "company_name": "Airborne Images",
    }

    template = get_template("money/taxes/form_4797_pdf.html")
    html_string = template.render(context)

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as output:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(output.name)
        output.seek(0)
        pdf = output.read()

    preview = request.GET.get("preview") == "1"
    disposition = "inline" if preview else "attachment"

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'{disposition}; filename="form_4797.pdf"'
    return response


# =============================================================================
# MILEAGE (unchanged from your pasted version except for one bug fix)
# =============================================================================

INTERNAL_REIMBURSED_TYPE = "Reimbursed"
IRS_DEDUCTIBLE_TYPES = ["Business"]

MILES_OUTPUT = DecimalField(max_digits=12, decimal_places=1)
ZERO_MILES = Value(0, output_field=MILES_OUTPUT)


def _get_mileage_rate(user, year: int) -> Decimal:
    obj = MileageRate.objects.filter(user=user, year=year).first()
    if obj and obj.rate is not None:
        return Decimal(str(obj.rate))
    return Decimal("0.7000")


def _miles_queryset(user, year: int, vehicle_id=None):
    qs = (
        Miles.objects.filter(user=user, date__year=year)
        .select_related("client", "event", "vehicle", "invoice_v2")
        .order_by("date", "id")
    )
    if vehicle_id:
        qs = qs.filter(vehicle_id=vehicle_id)

    miles_expr = ExpressionWrapper(
        Coalesce(F("total"), F("end") - F("begin"), Value(0)),
        output_field=MILES_OUTPUT,
    )
    return qs.annotate(miles=miles_expr)


def _vehicle_summary(user, year: int):
    vehicles = (
        Vehicle.objects.filter(user=user, miles__date__year=year)
        .distinct()
        .order_by("-is_active", "name")
    )

    year_rows = VehicleYear.objects.filter(vehicle__user=user, tax_year=year)
    year_map = {vy.vehicle_id: vy for vy in year_rows}

    qs = _miles_queryset(user, year)

    agg = qs.values("vehicle_id").annotate(
        business_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Business")), ZERO_MILES),
        commuting_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Commuting")), ZERO_MILES),
        other_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Other")), ZERO_MILES),
    )
    agg_map = {row["vehicle_id"]: row for row in agg}

    summary = []
    for v in vehicles:
        vy = year_map.get(v.id)
        row = agg_map.get(v.id, {})
        summary.append(
            {
                "vehicle": v,
                "odo_start": getattr(vy, "begin_mileage", None),
                "odo_end": getattr(vy, "end_mileage", None),
                "business_miles": row.get("business_miles", Decimal("0")),
                "commuting_miles": row.get("commuting_miles", Decimal("0")),
                "other_miles": row.get("other_miles", Decimal("0")),
            }
        )

    return summary


def _build_mileage_report_context(request):
    current_year = timezone.localdate().year
    year_param = request.GET.get("year")
    selected_year = int(year_param) if (year_param and year_param.isdigit()) else current_year

    vehicle_id = request.GET.get("vehicle") or ""
    vehicle = None
    if vehicle_id.isdigit():
        vehicle = Vehicle.objects.filter(user=request.user, pk=int(vehicle_id)).first()

    vehicles = Vehicle.objects.filter(user=request.user).order_by("-is_active", "name")
    mileage_rate = _get_mileage_rate(request.user, selected_year)

    entries_all = _miles_queryset(
        request.user,
        selected_year,
        vehicle_id=vehicle.pk if vehicle else None,
    )

    entries_irs = entries_all.filter(mileage_type__in=IRS_DEDUCTIBLE_TYPES)

    totals_all = entries_all.aggregate(
        business_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Business")), ZERO_MILES),
        commuting_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Commuting")), ZERO_MILES),
        other_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Other")), ZERO_MILES),
        reimbursed_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Reimbursed")), ZERO_MILES),
        total_miles=Coalesce(Sum("miles"), ZERO_MILES),
    )

    business_miles = totals_all["business_miles"] or Decimal("0")
    commuting_miles = totals_all["commuting_miles"] or Decimal("0")
    other_miles = totals_all["other_miles"] or Decimal("0")
    reimbursed_miles = totals_all["reimbursed_miles"] or Decimal("0")
    total_miles = totals_all["total_miles"] or Decimal("0")

    totals_irs = entries_irs.aggregate(
        irs_business_miles=Coalesce(Sum("miles"), ZERO_MILES),
    )
    irs_business_miles = totals_irs["irs_business_miles"] or Decimal("0")

    business_amount = business_miles * mileage_rate
    commuting_amount = commuting_miles * mileage_rate
    other_amount = other_miles * mileage_rate
    reimbursed_amount = reimbursed_miles * mileage_rate
    estimated_deduction = irs_business_miles * mileage_rate

    year_record = None
    if vehicle:
        year_record = VehicleYear.objects.filter(vehicle=vehicle, tax_year=selected_year).first()

    return {
        "current_page": "mileage",
        "selected_year": selected_year,
        "year_choices": list(range(2023, current_year + 1)),
        "vehicles": vehicles,
        "vehicle": vehicle,
        "year_record": year_record,
        "mileage_rate": mileage_rate,
        "entries": entries_all,
        "entries_irs": entries_irs,
        "vehicles_summary": _vehicle_summary(request.user, selected_year),
        "business_miles": business_miles,
        "commuting_miles": commuting_miles,
        "other_miles": other_miles,
        "reimbursed_miles": reimbursed_miles,
        "total_miles": total_miles,
        "business_amount": business_amount,
        "commuting_amount": commuting_amount,
        "other_amount": other_amount,
        "reimbursed_amount": reimbursed_amount,
        "irs_business_miles": irs_business_miles,
        "estimated_deduction": estimated_deduction,
        "taxable_miles": irs_business_miles,
        "taxable_dollars": estimated_deduction,
    }


@login_required
def mileage_log(request):
    ctx = _build_mileage_report_context(request)
    rate = ctx["mileage_rate"]

    entries = ctx["entries"].annotate(
        amount=ExpressionWrapper(
            Coalesce(F("miles"), Value(0)) * Value(rate),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by("-date", "-id")

    paginator = Paginator(entries, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx["mileage_list"] = page_obj.object_list
    ctx["page_obj"] = page_obj
    ctx["vehicle_choices"] = ctx["vehicles"]
    ctx["selected_vehicle_id"] = ctx["vehicle"].id if ctx["vehicle"] else None

    return render(request, "money/taxes/mileage_log.html", ctx)


@login_required
def mileage_report_pdf(request):
    context = _build_mileage_report_context(request)

    html_string = render_to_string(
        "money/taxes/mileage_report_pdf.html",
        context,
        request=request,
    )

    pdf_css = CSS(
        string="""
        @page { size: Letter; margin: 0.6in; }
        body { font-family: Arial, sans-serif; font-size: 10.5pt; color: #111; }
        h1 { font-size: 16pt; margin: 0 0 6px 0; }
        h2 { font-size: 12pt; margin: 14px 0 6px 0; }
        .muted { color: #555; }
        .row { display: flex; gap: 18px; }
        .box { border: 1px solid #ddd; padding: 10px; border-radius: 6px; }
        .w50 { width: 50%; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border-bottom: 1px solid #e5e5e5; padding: 6px 6px; vertical-align: top; }
        th { text-align: left; font-size: 10pt; background: #f3f3f3; }
        td.num, th.num { text-align: right; white-space: nowrap; }
        .footer { margin-top: 10px; font-size: 9pt; color: #666; }
        """
    )

    pdf_file = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf(stylesheets=[pdf_css])

    vehicle = context.get("vehicle")
    year = context["selected_year"]

    fname = f"mileage-report-{year}"
    if vehicle:
        safe_name = "".join(ch for ch in vehicle.name.lower().replace(" ", "-") if ch.isalnum() or ch == "-")
        fname += f"-{safe_name}"
    fname += ".pdf"

    resp = HttpResponse(pdf_file, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{fname}"'
    return resp


class MileageCreateView(LoginRequiredMixin, CreateView):
    model = Miles
    form_class = MileageForm
    template_name = "money/taxes/mileage_form.html"
    success_url = reverse_lazy("money:mileage_log")

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Mileage entry added successfully!")
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class MileageUpdateView(LoginRequiredMixin, UpdateView):
    model = Miles
    form_class = MileageForm
    template_name = "money/taxes/mileage_form.html"
    success_url = reverse_lazy("money:mileage_log")

    def get_queryset(self):
        return Miles.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Mileage entry updated successfully!")
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class MileageDeleteView(LoginRequiredMixin, DeleteView):
    model = Miles
    template_name = "money/taxes/mileage_confirm_delete.html"
    success_url = reverse_lazy("money:mileage_log")

    def get_queryset(self):
        return Miles.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Mileage entry deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "mileage"
        return context


@login_required
def update_mileage_rate(request):
    year_param = request.POST.get("year") if request.method == "POST" else request.GET.get("year")
    current_year = timezone.localdate().year
    selected_year = int(year_param) if (year_param and str(year_param).isdigit()) else current_year

    mileage_rate, _ = MileageRate.objects.get_or_create(
        user=request.user,
        year=selected_year,
        defaults={"rate": Decimal("0.7000")},
    )

    if request.method == "POST":
        form = MileageRateForm(request.POST, instance=mileage_rate)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.year = selected_year
            obj.save()
            messages.success(request, "Mileage rate updated successfully!")
            return redirect("money:mileage_log")
        messages.error(request, "Error updating mileage rate. Please check the form.")
    else:
        form = MileageRateForm(instance=mileage_rate)

    context = {
        "form": form,
        "current_page": "mileage",
        "selected_year": selected_year,
        "year_choices": list(range(2023, current_year + 1)),
    }
    return render(request, "money/taxes/update_mileage_rate.html", context)


@login_required
def export_mileage_csv(request):
    ctx = _build_mileage_report_context(request)

    rate = ctx["mileage_rate"]
    vehicle = ctx.get("vehicle")
    selected_year = ctx["selected_year"]

    qs = ctx["entries"].annotate(
        amount=ExpressionWrapper(
            Coalesce(F("miles"), Value(0)) * Value(rate),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by("date", "id")

    fname = f"mileage-log-{selected_year}"
    if vehicle:
        safe_name = "".join(ch for ch in vehicle.name.lower().replace(" ", "-") if ch.isalnum() or ch == "-")
        fname += f"-{safe_name}"
    fname += ".csv"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    writer = csv.writer(response)

    writer.writerow(
        [
            "Date",
            "Vehicle",
            "Client",
            "Invoice #",
            "Event",
            "Odo Begin",
            "Odo End",
            "Miles",
            "Amount",
            "Type",
        ]
    )

    for e in qs:
        if getattr(e, "invoice_v2_id", None) and getattr(e.invoice_v2, "invoice_number", None):
            invoice_number = e.invoice_v2.invoice_number
        else:
            invoice_number = getattr(e, "invoice_number", "") or ""

        vehicle_name = e.vehicle.name if getattr(e, "vehicle_id", None) and e.vehicle else ""
        client_name = str(e.client) if getattr(e, "client_id", None) and e.client else ""
        event_name = str(e.event) if getattr(e, "event_id", None) and e.event else ""

        writer.writerow(
            [
                e.date.strftime("%m/%d/%Y") if e.date else "",
                vehicle_name,
                client_name,
                invoice_number,
                event_name,
                f"{e.begin:.1f}" if e.begin is not None else "",
                f"{e.end:.1f}" if e.end is not None else "",
                f"{e.miles:.1f}" if getattr(e, "miles", None) is not None else "0.0",
                f"{e.amount:.2f}" if getattr(e, "amount", None) is not None else "0.00",
                getattr(e, "mileage_type", "") or "",
            ]
        )

    return response
