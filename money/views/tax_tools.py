# _FLIGHTPLAN/money/views/tax_tools.py

from __future__ import annotations

import csv
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from weasyprint import CSS, HTML

from ..forms.taxes.taxes import CategoryForm, MileageForm, MileageRateForm, SubCategoryForm
from ..models import Category, Miles, MileageRate, SubCategory, Vehicle, VehicleYear

logger = logging.getLogger(__name__)

# =============================================================================
# CATEGORIES
# =============================================================================


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "money/reports/category_page.html"
    context_object_name = "categories"

    def get_queryset(self):
        return (
            Category.objects.filter(user=self.request.user)
            .prefetch_related("subcategories")
            .order_by("category")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context



class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "money/reports/category_form.html"
    success_url = reverse_lazy("money:category_page")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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
    template_name = "money/reports/category_form.html"
    success_url = reverse_lazy("money:category_page")

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user  # ALWAYS pass user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = "money/reports/category_confirm_delete.html"
    success_url = reverse_lazy("money:category_page")

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Category deleted successfully!")
            return response
        except ProtectedError:
            messages.error(self.request, "Cannot delete category due to related transactions.")
            return redirect("money:category_page")
        except Exception:
            logger.exception("Error deleting category for user %s", request.user.id)
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
    template_name = "money/reports/sub_category_form.html"
    success_url = reverse_lazy("money:category_page")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user  
        return kwargs

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
    template_name = "money/reports/sub_category_form.html"
    success_url = reverse_lazy("money:category_page")
    context_object_name = "sub_cat"

    def get_queryset(self):
        return SubCategory.objects.filter(user=self.request.user).select_related("category")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Sub-Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context


class SubCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = SubCategory
    template_name = "money/reports/sub_category_confirm_delete.html"
    success_url = reverse_lazy("money:category_page")

    def get_queryset(self):
        return SubCategory.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Sub-Category deleted successfully!")
            return response
        except ProtectedError:
            messages.error(self.request, "Cannot delete sub-category due to related transactions.")
            return redirect("money:category_page")
        except Exception:
            logger.exception("Error deleting sub-category for user %s", request.user.id)
            messages.error(self.request, "Error deleting sub-category.")
            return redirect("money:category_page")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "categories"
        return context





# =============================================================================
# MILEAGE
# =============================================================================

IRS_DEDUCTIBLE_TYPES = ["Business"]

MILES_OUTPUT = DecimalField(max_digits=12, decimal_places=1)
ZERO_MILES = Value(0, output_field=MILES_OUTPUT)


def _get_mileage_rate(user, year: int) -> Decimal:
    """
    MileageRate supports:
    - per-user override (user=<user>)
    - optional global default (user is NULL)
    """
    obj = MileageRate.objects.filter(user=user, year=year).first()
    if obj and obj.rate is not None:
        return Decimal(str(obj.rate))

    global_obj = MileageRate.objects.filter(user__isnull=True, year=year).first()
    if global_obj and global_obj.rate is not None:
        return Decimal(str(global_obj.rate))

    return Decimal("0.7000")




MILES_OUTPUT = DecimalField(max_digits=10, decimal_places=1)

def _miles_queryset(user, year: int, vehicle_id=None):
    qs = (
        Miles.objects.filter(user=user, date__year=year)
        .select_related("client", "event", "vehicle", "invoice_v2")
        .order_by("date", "id")
    )
    if vehicle_id:
        qs = qs.filter(vehicle_id=vehicle_id)

    miles_expr = ExpressionWrapper(
        Coalesce(F("total"), F("end") - F("begin"), Value(Decimal("0.0"))),
        output_field=MILES_OUTPUT,
    )
    return qs.annotate(miles=miles_expr)




ZERO_MILES = Decimal("0.0") 

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
                "business_miles": row.get("business_miles", ZERO_MILES),
                "commuting_miles": row.get("commuting_miles", ZERO_MILES),
                "other_miles": row.get("other_miles", ZERO_MILES),
                # optional:
                # "reimbursed_miles": row.get("reimbursed_miles", ZERO_MILES),
            }
        )
    return summary

AMOUNT_OUTPUT = DecimalField(max_digits=12, decimal_places=2)

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
        vehicle_id=vehicle.pk if vehicle else None
    )

    entries_irs = entries_all.filter(mileage_type__in=IRS_DEDUCTIBLE_TYPES)

    totals_all = entries_all.aggregate(
        business_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Business")), ZERO_MILES),
        commuting_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Commuting")), ZERO_MILES),
        other_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Other")), ZERO_MILES),
        reimbursed_miles=Coalesce(Sum("miles", filter=Q(mileage_type="Reimbursed")), ZERO_MILES),
        total_miles=Coalesce(Sum("miles"), ZERO_MILES),
    )

    business_miles = totals_all["business_miles"] or ZERO_MILES
    commuting_miles = totals_all["commuting_miles"] or ZERO_MILES
    other_miles = totals_all["other_miles"] or ZERO_MILES
    reimbursed_miles = totals_all["reimbursed_miles"] or ZERO_MILES
    total_miles = totals_all["total_miles"] or ZERO_MILES

    totals_irs = entries_irs.aggregate(
        irs_business_miles=Coalesce(Sum("miles"), ZERO_MILES),
    )
    irs_business_miles = totals_irs["irs_business_miles"] or ZERO_MILES

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





class MileageCreateView(LoginRequiredMixin, CreateView):
    model = Miles
    form_class = MileageForm
    template_name = "money/taxes/mileage_form.html"
    success_url = reverse_lazy("money:mileage_log")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # ✅ happens BEFORE form.is_valid()
        if not form.instance.user_id:
            form.instance.user = self.request.user
        return form

    def form_valid(self, form):
        messages.success(self.request, "Mileage entry added successfully!")
        return super().form_valid(form)




class MileageUpdateView(LoginRequiredMixin, UpdateView):
    model = Miles
    form_class = MileageForm
    template_name = "money/taxes/mileage_form.html"
    success_url = reverse_lazy("money:mileage_log")

    def get_queryset(self):
        return Miles.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Mileage entry updated successfully!")
        return super().form_valid(form)






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
def mileage_log(request):
    ctx = _build_mileage_report_context(request)
    rate = ctx["mileage_rate"]

    entries = (
        ctx["entries"]
        .annotate(
            amount=ExpressionWrapper(
                Coalesce(F("miles"), Value(0)) * Value(rate),
                output_field=AMOUNT_OUTPUT,
            )
        )
        .order_by("-date", "-id")
    )

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
        safe_name = "".join(
            ch for ch in vehicle.name.lower().replace(" ", "-") if ch.isalnum() or ch == "-"
        )
        fname += f"-{safe_name}"
    fname += ".pdf"

    resp = HttpResponse(pdf_file, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{fname}"'
    return resp


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
        form = MileageRateForm(request.POST, instance=mileage_rate, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.year = selected_year
            obj.save()
            messages.success(request, "Mileage rate updated successfully!")
            return redirect("money:mileage_log")
        messages.error(request, "Error updating mileage rate. Please check the form.")
    else:
        form = MileageRateForm(instance=mileage_rate, user=request.user)

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
        safe_name = "".join(
            ch for ch in vehicle.name.lower().replace(" ", "-") if ch.isalnum() or ch == "-"
        )
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
        event_name = e.event.title if getattr(e, "event_id", None) and e.event else ""

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
