# money/views/contractors.py

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from money.forms.contractors.contractors import ContractorForm
from money.models import Contractor, Transaction


class UserScopedQuerysetMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)


class ContractorListView(LoginRequiredMixin, UserScopedQuerysetMixin, ListView):
    model = Contractor
    template_name = "money/contractors/contractor_list.html"
    context_object_name = "contractors"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().filter(is_active=True)

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(business_name__icontains=q)
                | Q(email__icontains=q)
                | Q(contractor_number__icontains=q)
            )

        return qs.order_by("last_name", "first_name", "id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["current_page"] = "contractors"
        return ctx


class ContractorCreateView(LoginRequiredMixin, CreateView):
    model = Contractor
    form_class = ContractorForm
    template_name = "money/contractors/contractor_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.user = self.request.user
        return form

    def get_success_url(self):
        return reverse_lazy("money:contractor_detail", kwargs={"pk": self.object.pk})


class ContractorUpdateView(LoginRequiredMixin, UserScopedQuerysetMixin, UpdateView):
    model = Contractor
    form_class = ContractorForm
    template_name = "money/contractors/contractor_form.html"

    def get_success_url(self):
        return reverse_lazy("money:contractor_detail", kwargs={"pk": self.object.pk})


class ContractorDetailView(LoginRequiredMixin, UserScopedQuerysetMixin, DetailView):
    model = Contractor
    template_name = "money/contractors/contractor_detail.html"
    context_object_name = "contractor"

    def _selected_year(self) -> int:
        y = self.request.GET.get("year")
        try:
            return int(y) if y else timezone.localdate().year
        except (TypeError, ValueError):
            return timezone.localdate().year

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        year = self._selected_year()
        contractor = self.object

        tx_qs = (
            Transaction.objects
            .filter(user=self.request.user, contractor=contractor, date__year=year)
            .select_related("category", "sub_cat", "event", "team")
            .order_by("-date", "-id")
        )

        total = tx_qs.aggregate(total=Sum("amount"))["total"] or 0

        years = (
            Transaction.objects
            .filter(user=self.request.user, contractor=contractor)
            .dates("date", "year")
        )
        year_choices = sorted({d.year for d in years} | {timezone.localdate().year}, reverse=True)

        ctx.update(
            {
                "selected_year": year,
                "year_choices": year_choices,
                "transactions": tx_qs,
                "transaction_total": total,
                "current_page": "contractors",
            }
        )
        return ctx


class ContractorDeleteView(LoginRequiredMixin, UserScopedQuerysetMixin, DeleteView):
    model = Contractor
    template_name = "money/contractors/contractor_confirm_delete.html"
    success_url = reverse_lazy("money:contractor_list")
