import re
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.templatetags.static import static 
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST
from django.views.generic import (
    TemplateView, UpdateView, ListView, DetailView, DeleteView, FormView
)
from django.db import transaction, IntegrityError
from django.contrib.staticfiles.storage import staticfiles_storage

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False

from .forms import *
from .models import *



def safe_int(value):
    """Parse an int from mixed strings like '85%', ' 1,234 ', or None."""
    try:
        if value is None:
            return None
        s = re.sub(r'[^0-9\-]+', '', str(value))
        return int(s) if s not in ("", "-", None, "") else None
    except Exception:
        return None

def safe_float(value):
    """Parse a float from mixed strings like '1,234.56 mph', or None."""
    try:
        if value is None:
            return None
        s = re.sub(r'[^0-9\.\-]+', '', str(value))
        return float(s) if s not in ("", "-", ".", None) else None
    except Exception:
        return None

def safe_pct(value):
    """Parse a percent value that may contain '%' or whitespace."""
    return safe_int(str(value).replace('%', '')) if value is not None else None

def extract_state(address):
    """Pull a 2-letter state abbreviation from addresses like 'City, ST, USA'."""
    match = re.search(r",\s*([A-Z]{2})[, ]", address or "")
    return match.group(1) if match else None



class OpsPlanCreateView(LoginRequiredMixin, View):
    """
    Create a new OpsPlan for a given Event and immediately redirect to Edit.
    URL: /operations/events/<event_id>/ops-plans/new/?year=YYYY
    """

    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        year_qs = request.GET.get("year")
        try:
            plan_year = int(year_qs) if year_qs else timezone.now().year
        except (TypeError, ValueError):
            plan_year = timezone.now().year

        try:
            with transaction.atomic():
                plan = OpsPlan.objects.create(
                    event=event,
                    event_name=str(event),   
                    plan_year=plan_year,
                    status=getattr(OpsPlan, "DRAFT", "Draft"),
                    created_by=request.user,
                    updated_by=request.user,
                )
                messages.success(request, "Draft Ops Plan created.")
        except IntegrityError:
            plan = OpsPlan.objects.filter(event=event, plan_year=plan_year).first()
            if plan:
                messages.info(request, "An Ops Plan for this event and year already exists. Redirected to that plan.")
            else:
                messages.error(request, "Could not create Ops Plan (unique constraint).")
                return redirect(reverse_lazy("ops_plan_list"))

        return redirect("ops_plan_update", pk=plan.pk)


class OpsPlanUpdateView(LoginRequiredMixin, UpdateView):
    model = OpsPlan
    form_class = OpsPlanForm
    template_name = "operations/ops_plan_create.html"
    context_object_name = "plan"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.object.event
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        status_choices = getattr(self.model, "STATUS_CHOICES", None)
        if status_choices:
            ctx["statuses"] = [label for (value, label) in status_choices] if isinstance(status_choices[0], (tuple, list)) else status_choices
        else:
            ctx["statuses"] = ["Draft", "In Review", "Approved", "Archived"]
        return ctx

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Ops Plan updated.")
        return super().form_valid(form)

    def get_success_url(self):
        if hasattr(self.object, "get_absolute_url"):
            return self.object.get_absolute_url()
        return reverse("ops_plan_update", kwargs={"pk": self.object.pk})


class OpsPlanDeleteView(LoginRequiredMixin, DeleteView):
    model = OpsPlan
    template_name = "operations/ops_plan_confirm_delete.html"
    context_object_name = "plan"

    def get_success_url(self):
        messages.success(self.request, "Ops Plan deleted.")
        return reverse("ops_plan_list", args=[self.object.event_id])


@login_required
def ops_plan_pdf_view(request, pk):
    plan = get_object_or_404(OpsPlan, pk=pk)

    if not WEASYPRINT_AVAILABLE:
        return HttpResponse(
            "PDF generation requires WeasyPrint. Install with 'pip install weasyprint'.",
            status=501, content_type="text/plain"
        )

    try:
        logo_fs_path = staticfiles_storage.path('images/logo2.png')
        logo_url = Path(logo_fs_path).as_uri() 
    except Exception:
        logo_url = request.build_absolute_uri(static('images/logo2.png'))
        
    brand_name = getattr(settings, "BRAND", {}).get("name") or getattr(settings, "SITE_NAME", "operations")

    html = render_to_string(
        "operations/ops_plan_pdf.html",
        {
            "plan": plan,
            "generated_at": timezone.now(),
            "logo_url": logo_url,
            "brand_name": brand_name,
        },
    )
    if getattr(settings, "STATIC_ROOT", None):
        base_url = Path(settings.STATIC_ROOT).as_uri()
    else:
        base_url = Path(settings.BASE_DIR).as_uri()

    pdf = HTML(string=html, base_url=base_url).write_pdf(
        stylesheets=[CSS(string="""@page { size: A4; margin: 18mm 16mm; }""")]
    )

    filename = f"ops-plan-{plan.id}-{plan.plan_year}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp




class OpsPlanIndexView(LoginRequiredMixin, TemplateView):
    template_name = "operations/ops_plan_index.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["plans"] = (
            OpsPlan.objects.select_related("event", "client")
            .order_by("-updated_at")[:50]
        )
        ctx["events"] = Event.objects.order_by("-id")[:200]
        ctx["current_year"] = timezone.now().year
        ctx["statuses"] = [
            OpsPlan.DRAFT,
            OpsPlan.IN_REVIEW,
            OpsPlan.APPROVED,
            OpsPlan.ARCHIVED,
        ]

        return ctx



class OpsPlanListView(LoginRequiredMixin, ListView):
    template_name = "operations/ops_plan_list.html"
    context_object_name = "plans"

    def get_queryset(self):
        self.event = get_object_or_404(Event, pk=self.kwargs["event_id"])
        return OpsPlan.objects.filter(event=self.event).order_by("-updated_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["event"] = self.event
        return ctx
    


class OpsPlanDetailView(LoginRequiredMixin, DetailView):
    model = OpsPlan
    template_name = "operations/ops_plan_detail.html"
    context_object_name = "plan"



@require_POST
@login_required
def ops_plan_submit_view(request, pk):
    """Draft -> In Review (author action)"""
    plan = get_object_or_404(OpsPlan, pk=pk)
    if plan.status != OpsPlan.DRAFT:
        messages.warning(request, f"Only Draft plans can be submitted (current status: {plan.status}).")
        return redirect(plan.get_absolute_url())

    plan.status = OpsPlan.IN_REVIEW
    plan.updated_by = request.user
    plan.save(update_fields=["status", "updated_by", "updated_at"])
    messages.success(request, "Ops Plan submitted for review.")
    return redirect(plan.get_absolute_url())



@require_POST
@staff_member_required
def ops_plan_approve_view(request, pk):
    """In Review -> Approved (staff action)"""
    plan = get_object_or_404(OpsPlan, pk=pk)
    if plan.status != OpsPlan.IN_REVIEW:
        messages.warning(request, f"Only plans In Review can be approved (current status: {plan.status}).")
        return redirect(plan.get_absolute_url())

    plan.status = OpsPlan.APPROVED
    plan.updated_by = request.user
    plan.save(update_fields=["status", "updated_by", "updated_at"])
    messages.success(request, "Ops Plan approved.")
    return redirect(plan.get_absolute_url())


@require_POST
@staff_member_required
def ops_plan_archive_view(request, pk):
    """Any -> Archived (staff action)"""
    plan = get_object_or_404(OpsPlan, pk=pk)
    if plan.status == OpsPlan.ARCHIVED:
        messages.info(request, "This Ops Plan is already archived.")
        return redirect(plan.get_absolute_url())

    plan.status = OpsPlan.ARCHIVED
    plan.updated_by = request.user
    plan.save(update_fields=["status", "updated_by", "updated_at"])
    messages.success(request, "Ops Plan archived.")
    return redirect(plan.get_absolute_url())




class OpsPlanApprovalView(FormView):
    template_name = "operations/ops_plan_approve.html"
    form_class = OpsPlanApprovalForm

    def dispatch(self, request, *args, **kwargs):
        self.plan = get_object_or_404(OpsPlan, pk=kwargs["pk"], approval_token=kwargs["token"])
        if self.plan.approved_at:
            return render(request, "flightlogs/ops_plan_already_approved.html", {"plan": self.plan})
        if self.plan.approval_token_expires_at and timezone.now() > self.plan.approval_token_expires_at:
            return render(request, "flightlogs/ops_plan_expired.html", {"plan": self.plan})
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["plan"] = self.plan
        return ctx

    def form_valid(self, form):
        self.plan.approved_name = form.cleaned_data["full_name"]
        self.plan.approved_at = timezone.now()
        self.plan.approved_ip = self.request.META.get("REMOTE_ADDR", "")
        self.plan.approved_user_agent = self.request.META.get("HTTP_USER_AGENT", "")
        self.plan.approved_notes_snapshot = self.plan.notes
        self.plan.compute_attestation_hash()
        self.plan.status = OpsPlan.APPROVED
        self.plan.approval_token = None  # invalidate token
        self.plan.save()

        return render(self.request, "operations/ops_plan_approved_success.html", {"plan": self.plan})



@require_POST
def change_ops_plan_status(request, pk, new_status):
    plan = get_object_or_404(OpsPlan, pk=pk)

    # Validate that the requested status is valid
    valid_statuses = [OpsPlan.DRAFT, OpsPlan.IN_REVIEW, OpsPlan.APPROVED, OpsPlan.ARCHIVED]
    if new_status not in valid_statuses:
        messages.error(request, f"Invalid status '{new_status}'.")
        return redirect("ops_plan_index")

    # Update the plan
    plan.status = new_status
    plan.save()

    messages.success(request, f"Ops Plan '{plan.event_name or plan.event}' updated to {new_status}.")
    return redirect("ops_plan_index")



class OpsPlanView(LoginRequiredMixin, TemplateView):
    template_name = "money/operations/ops_plan.html"