from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.urls import reverse_lazy
from decimal import Decimal
from django.utils import timezone
from django.db.models import F, Q, Sum, Value, DecimalField
from django.db.models.functions import Coalesce


from django.views.generic import (
        ListView, 
        CreateView, 
        UpdateView, 
        DeleteView, 
        DetailView
)

from ..models import (
        Vehicle, 
        Miles, 
        VehicleYear, 
        VehicleExpense, 
        MileageRate
)

from ..forms.vehicles import (
        VehicleForm, 
        VehicleYearFormSet,
)



class VehicleListView(LoginRequiredMixin, ListView):
    model = Vehicle
    template_name = "money/taxes/vehicle_list.html"
    context_object_name = "vehicles"

    def get_queryset(self):
        return Vehicle.objects.filter(user=self.request.user).order_by("-is_active", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "mileage"
        return context




class VehicleCreateView(LoginRequiredMixin, CreateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = "money/taxes/vehicle_form.html"
    success_url = reverse_lazy("money:vehicle_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["mode"] = "add"
        context["vehicle"] = None

        if self.request.method == "POST":
            context["year_formset"] = VehicleYearFormSet(self.request.POST)
        else:
            context["year_formset"] = VehicleYearFormSet()

        context["current_page"] = "mileage"
        return context


    def form_valid(self, form):
        context = self.get_context_data()
        year_formset = context["year_formset"]

        form.instance.user = self.request.user

        if not year_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        with transaction.atomic():
            response = super().form_valid(form)
            year_formset.instance = self.object
            year_formset.save()

        messages.success(self.request, "Vehicle added successfully!")
        return response




class VehicleUpdateView(LoginRequiredMixin, UpdateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = "money/taxes/vehicle_form.html"
    success_url = reverse_lazy("money:vehicle_list")

    def get_queryset(self):
        return Vehicle.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["mode"] = "edit"
        context["vehicle"] = self.object

        if self.request.method == "POST":
            context["year_formset"] = VehicleYearFormSet(self.request.POST, instance=self.object)
        else:
            context["year_formset"] = VehicleYearFormSet(instance=self.object)

        context["current_page"] = "mileage"
        return context


    def form_valid(self, form):
        context = self.get_context_data()
        year_formset = context["year_formset"]

        if not year_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        with transaction.atomic():
            response = super().form_valid(form)
            year_formset.save()

        messages.success(self.request, "Vehicle updated successfully!")
        return response


class VehicleDeleteView(LoginRequiredMixin, DeleteView):
    model = Vehicle
    template_name = "money/taxes/vehicle_confirm_delete.html"
    success_url = reverse_lazy("money:vehicle_list")

    def get_queryset(self):
        return Vehicle.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Vehicle deleted successfully!")
        return super().delete(request, *args, **kwargs)



class VehicleDetailView(LoginRequiredMixin, DetailView):
    model = Vehicle
    template_name = "money/taxes/vehicle_detail.html"
    context_object_name = "vehicle"

    def get_queryset(self):
        return Vehicle.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        current_year = timezone.localdate().year
        year_param = self.request.GET.get("year")
        selected_year = int(year_param) if (year_param and year_param.isdigit()) else current_year

        rate_obj = MileageRate.objects.filter(user=self.request.user, year=selected_year).first()
        mileage_rate = Decimal(str(rate_obj.rate)) if rate_obj and rate_obj.rate is not None else Decimal("0.7000")

        year_record = VehicleYear.objects.filter(vehicle=self.object, tax_year=selected_year).first()

        miles_qs = (
            Miles.objects
            .filter(user=self.request.user, vehicle=self.object, date__year=selected_year)
            .select_related("client", "event", "invoice_v2")
            .order_by("-date")
        )

        ZERO_MILES = Value(0, output_field=DecimalField(max_digits=12, decimal_places=1))

        totals = miles_qs.aggregate(
            taxable_miles=Coalesce(Sum("total", filter=Q(mileage_type="Business")), ZERO_MILES),
            reimbursed_miles=Coalesce(Sum("total", filter=Q(mileage_type="Reimbursed")), ZERO_MILES),
            total_miles=Coalesce(Sum("total"), ZERO_MILES),
        )

        taxable_miles = totals["taxable_miles"] or Decimal("0")
        reimbursed_miles = totals["reimbursed_miles"] or Decimal("0")
        total_miles = totals["total_miles"] or Decimal("0")
        taxable_dollars = taxable_miles * mileage_rate

        expenses_qs = (
            VehicleExpense.objects
            .filter(user=self.request.user, vehicle=self.object, date__year=selected_year)
            .order_by("-date")
        )

        expense_totals = expenses_qs.aggregate(
            total=Coalesce(
                Sum("amount"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )
        total_expenses = expense_totals["total"] or Decimal("0")

        context.update({
            "current_page": "mileage",
            "selected_year": selected_year,
            "year_choices": list(range(2023, current_year + 1)),
            "mileage_rate": mileage_rate,
            "year_record": year_record,
            "miles_qs": miles_qs,
            "taxable_miles": taxable_miles,
            "reimbursed_miles": reimbursed_miles,
            "total_miles": total_miles,
            "taxable_dollars": taxable_dollars,
            "expenses_qs": expenses_qs[:10],
            "total_expenses": total_expenses,
        })
        return context