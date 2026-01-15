# money/views/company_profiles.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ..forms.company_profile.company_profile import CompanyProfileForm
from ..models import CompanyProfile


def _staff_check(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return _staff_check(self.request.user)


class CompanyProfileListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = CompanyProfile
    template_name = "money/company_profiles/companyprofile_list.html"
    context_object_name = "profiles"
    paginate_by = 25


class CompanyProfileDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = CompanyProfile
    template_name = "money/company_profiles/companyprofile_detail.html"
    context_object_name = "profile"


class CompanyProfileCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = CompanyProfile
    form_class = CompanyProfileForm
    template_name = "money/company_profiles/companyprofile_form.html"

    def get_success_url(self):
        messages.success(self.request, "Company profile created.")
        return reverse_lazy("money:companyprofile_detail", kwargs={"pk": self.object.pk})


class CompanyProfileUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = CompanyProfile
    form_class = CompanyProfileForm
    template_name = "money/company_profiles/companyprofile_form.html"

    def get_success_url(self):
        messages.success(self.request, "Company profile updated.")
        return reverse_lazy("money:companyprofile_detail", kwargs={"pk": self.object.pk})


class CompanyProfileDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = CompanyProfile
    template_name = "money/company_profiles/companyprofile_confirm_delete.html"
    success_url = reverse_lazy("money:companyprofile_list")

    def form_valid(self, form):
        messages.success(self.request, "Company profile deleted.")
        return super().form_valid(form)


@login_required
@user_passes_test(_staff_check)
@require_POST
def companyprofile_activate(request, pk: int):
    profile = get_object_or_404(CompanyProfile, pk=pk)

    with transaction.atomic():
        CompanyProfile.objects.filter(is_active=True).exclude(pk=profile.pk).update(is_active=False)
        profile.is_active = True
        profile.full_clean()
        profile.save(update_fields=["is_active", "updated_at"])

    messages.success(request, f"Activated: {profile.name_for_display}")
    return redirect("money:companyprofile_list")
