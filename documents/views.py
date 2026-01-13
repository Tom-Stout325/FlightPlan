from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from formtools.wizard.views import SessionWizardView

from .forms import (
    EnvironmentalConditionsForm,
    EquipmentDetailsForm,
    EventDetailsForm,
    GeneralDocumentForm,
    GeneralInfoForm,
    ImpactForm,
    ResponseForm,
    RootCauseForm,
    SignatureForm,
    SOPDocumentForm,
    WitnessForm,
)
from .models import DroneIncidentReport, GeneralDocument, SOPDocument

try:
    from weasyprint import CSS, HTML

    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False


# -------------------------------------------------
# Portal
# -------------------------------------------------
@login_required
def documents(request: HttpRequest) -> HttpResponse:
    return render(request, "documents/drone_portal.html", {"current_page": "documents"})


# -------------------------------------------------
# Incident Reporting (User-scoped)
# -------------------------------------------------
@login_required
def incident_reporting_system(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()

    reports = DroneIncidentReport.objects.filter(user=request.user).order_by("-report_date")

    if q:
        reports = reports.filter(
            Q(reported_by__icontains=q) |
            Q(location__icontains=q) |
            Q(description__icontains=q)
        )

    return render(
        request,
        "documents/incident_reporting_system.html",
        {
            "incident_reports": reports,
            "search_query": q,
            "current_page": "incidents",
        },
    )


@login_required
def incident_report_detail(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(DroneIncidentReport, user=request.user, pk=pk)
    return render(
        request,
        "documents/incident_report_detail.html",
        {"report": report, "current_page": "incidents"},
    )


@login_required
def incident_report_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    if not WEASYPRINT_AVAILABLE:
        messages.error(request, "PDF generation is not available (WeasyPrint not installed).")
        return redirect("documents:incident_reporting_system")

    report = get_object_or_404(DroneIncidentReport, user=request.user, pk=pk)

    html_string = render_to_string(
        "documents/incident_report_pdf.html",
        {"report": report, "current_page": "incidents"},
        request=request,
    )

    pdf_content = HTML(string=html_string).write_pdf(
        stylesheets=[CSS(string="@page { size: Letter; margin: 0.5in; }")]
    )

    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="incident_report_{pk}.pdf"'
    return response


WIZARD_FORMS = [
    ("general", GeneralInfoForm),
    ("event", EventDetailsForm),
    ("impact", ImpactForm),
    ("equipment", EquipmentDetailsForm),
    ("environment", EnvironmentalConditionsForm),
    ("witness", WitnessForm),
    ("response", ResponseForm),
    ("cause", RootCauseForm),
    ("signature", SignatureForm),
]


class IncidentReportWizard(LoginRequiredMixin, SessionWizardView):
    form_list = WIZARD_FORMS

    def get_template_names(self):
        # reuse your single wizard template
        return ["documents/wizard_form.html"]

    def get(self, request, *args, **kwargs):
        # start fresh each time
        self.storage.reset()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        current_step = self.steps.step1 + 1
        total_steps = self.steps.count
        context.update(
            {
                "current_step": current_step,
                "total_steps": total_steps,
                "progress_percent": int((current_step / total_steps) * 100),
                "current_page": "incidents",
            }
        )
        return context

    def done(self, form_list, **kwargs):
        data = {}
        for form in form_list:
            data.update(form.cleaned_data)

        # ✅ user scoped create
        report = DroneIncidentReport.objects.create(user=self.request.user, **data)
        messages.success(self.request, "Incident report submitted.")
        return redirect("documents:incident_report_detail", pk=report.pk)


# -------------------------------------------------
# SOPs (User-scoped)
# -------------------------------------------------
@login_required
def sop_list(request: HttpRequest) -> HttpResponse:
    sops = SOPDocument.objects.filter(user=request.user).order_by("-created_at")
    return render(
        request,
        "documents/sop_list.html",
        {"sops": sops, "current_page": "sop"},
    )


@login_required
def sop_upload(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = SOPDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user  # ✅ user scoped
            obj.save()
            messages.success(request, "SOP added successfully.")
            return redirect("documents:sop_list")
        messages.error(request, "There was a problem uploading the SOP.")
    else:
        form = SOPDocumentForm()

    return render(
        request,
        "documents/sop_upload.html",
        {"form": form, "current_page": "sop"},
    )


@login_required
def delete_sop(request: HttpRequest, pk: int) -> HttpResponse:
    sop = get_object_or_404(SOPDocument, user=request.user, pk=pk)
    if request.method == "POST":
        title = sop.title
        sop.delete()
        messages.success(request, f"SOP '{title}' deleted successfully.")
    return redirect("documents:sop_list")


# -------------------------------------------------
# General Documents (User-scoped)
# -------------------------------------------------
@login_required
def general_document_list(request: HttpRequest) -> HttpResponse:
    search_query = (request.GET.get("q") or "").strip()
    selected_category = (request.GET.get("category") or "").strip()

    docs = GeneralDocument.objects.filter(user=request.user).order_by("-uploaded_at")

    if search_query:
        docs = docs.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))

    if selected_category:
        docs = docs.filter(category=selected_category)

    categories = (
        GeneralDocument.objects.filter(user=request.user)
        .values_list("category", flat=True)
        .distinct()
        .order_by("category")
    )

    paginator = Paginator(docs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "documents/general_list.html",
        {
            "documents": page_obj,
            "page_obj": page_obj,
            "categories": categories,
            "selected_category": selected_category,
            "search_query": search_query,
            "current_page": "documents",
        },
    )


@login_required
def upload_general_document(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = GeneralDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user  # ✅ user scoped
            obj.save()
            messages.success(request, "Document added successfully.")
            return redirect("documents:general_document_list")
        messages.error(request, "There was a problem uploading the document.")
    else:
        form = GeneralDocumentForm()

    return render(
        request,
        "documents/upload_general.html",
        {"form": form, "current_page": "documents"},
    )


@login_required
def delete_document(request: HttpRequest, pk: int) -> HttpResponse:
    doc = get_object_or_404(GeneralDocument, user=request.user, pk=pk)
    if request.method == "POST":
        doc.delete()
        messages.success(request, "Document deleted successfully.")
    return redirect("documents:general_document_list")
