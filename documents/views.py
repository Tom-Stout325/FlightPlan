import os
import re
import uuid
from datetime import datetime
from django.conf import settings
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.views.generic import (
    TemplateView,
    UpdateView,
    ListView,
    DetailView,
    DeleteView,
)

from django.db.models import Q
from formtools.wizard.views import SessionWizardView

from .models import (
    DroneIncidentReport,
    SOPDocument,
    GeneralDocument,
)

from .forms import (
    SOPDocumentForm,
    GeneralDocumentForm,
    GeneralInfoForm,
    EventDetailsForm,
    EquipmentDetailsForm,
    EnvironmentalConditionsForm,
    WitnessForm,
    ActionTakenForm,
    FollowUpForm,
)

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False


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



# -------------------------------------------------
# D O C U M E N T S
# -------------------------------------------------


@login_required
def documents(request):
    context = {'current_page': 'documents'}
    return render(request, 'documents/drone_portal.html', context)


@login_required
def incident_reporting_system(request):
    query = request.GET.get('q', '').strip()
    reports = DroneIncidentReport.objects.all().order_by('-report_date')
    if query:
        reports = reports.filter(
            Q(reported_by__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query)
        )
    context = {
        'incident_reports': reports,
        'search_query': query,
        'current_page': 'incidents',
    }
    return render(request, 'documents/incident_reporting_system.html', context)


@login_required
def incident_report_pdf(request, pk):
    report = get_object_or_404(DroneIncidentReport, pk=pk)
    logo_path = request.build_absolute_uri(static("images/logo2.png"))
    context = {
        'report': report,
        'logo_path': logo_path,
        'now': datetime.now(),
        'current_page': 'incidents',
    }
    html_string = render_to_string('documents/incident_report_pdf.html', context, request=request)
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    pdf_content = html.write_pdf()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="incident_report_{pk}.pdf"'
    response.write(pdf_content)
    return response


FORMS = [
    ("general", GeneralInfoForm),
    ("event", EventDetailsForm),
    ("equipment", EquipmentDetailsForm),
    ("environment", EnvironmentalConditionsForm),
    ("witness", WitnessForm),
    ("action", ActionTakenForm),
    ("followup", FollowUpForm),
]

TEMPLATES = {
    "general": "documents/wizard_form.html",
    "event": "documents/wizard_form.html",
    "equipment": "documents/wizard_form.html",
    "environment": "documents/wizard_form.html",
    "witness": "documents/wizard_form.html",
    "action": "documents/wizard_form.html",
    "followup": "documents/wizard_form.html",
}


class IncidentReportWizard(LoginRequiredMixin, SessionWizardView):
    template_name = 'documents/incident_report_form.html'

    def get(self, request, *args, **kwargs):
        self.storage.reset()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        current_step = self.steps.step1 + 1
        total_steps = self.steps.count
        progress_percent = int((current_step / total_steps) * 100)
        context.update({
            'current_step': current_step,
            'total_steps': total_steps,
            'progress_percent': progress_percent,
            'current_page': 'incidents',
        })
        return context

    def done(self, form_list, **kwargs):
        data = {}
        for form in form_list:
            data.update(form.cleaned_data)

        report = DroneIncidentReport.objects.create(**data)

        context = {'report': report, 'current_page': 'incidents'}
        html_string = render_to_string('documents/incident_report_pdf.html', context, request=self.request)
        html = HTML(string=html_string, base_url=self.request.build_absolute_uri())
        pdf_content = html.write_pdf()

        unique_id = uuid.uuid4()
        filename = f'documents/incident_report_{report.pk}_{unique_id}.pdf'
        filepath = os.path.join(settings.MEDIA_ROOT, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(pdf_content)

        pdf_url = os.path.join(settings.MEDIA_URL, filename)
        context = {'form_data': data, 'pdf_url': pdf_url, 'current_page': 'incidents'}
        return render(self.request, 'documents/incident_report_success.html', context)


@login_required
def incident_report_success(request):
    pdf_url = request.GET.get('pdf_url')
    context = {'pdf_url': pdf_url, 'current_page': 'incidents'}
    return render(request, 'documents/report_success.html', context)


@login_required
def incident_report_list(request):
    query = request.GET.get('q', '').strip()
    reports = DroneIncidentReport.objects.all()
    if query:
        reports = reports.filter(
            Q(reported_by__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query)
        )
    context = {
        'incident_reports': reports.order_by('-report_date'),
        'search_query': query,
        'current_page': 'incidents',
    }
    return render(request, 'documents/incident_reporting_system.html', context)


@login_required
def incident_report_detail(request, pk):
    report = get_object_or_404(DroneIncidentReport, pk=pk)
    context = {'report': report, 'current_page': 'incidents'}
    return render(request, 'documents/incident_report_detail.html', context)


@login_required
def sop_upload(request):
    if request.method == 'POST':
        form = SOPDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "SOP added successfully.")
            return redirect('sop_list')
        messages.error(request, "There was a problem uploading the document.")
    else:
        form = SOPDocumentForm()
    return render(request, 'documents/sop_upload.html', {'form': form, 'current_page': 'sop'})


@login_required
def sop_list(request):
    query = request.GET.get('q', '').strip()
    sops = SOPDocument.objects.all()
    if query:
        sops = sops.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    sops = sops.order_by('-created_at')

    paginator = Paginator(sops, 10)  # ✅ removed stray period
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'sops': page_obj,
        'page_obj': page_obj,
        'search_query': query,
        'current_page': 'sop',
    }
    return render(request, 'documents/sop_list.html', context)



@login_required
def delete_sop(request, pk):
    sop = get_object_or_404(SOPDocument, pk=pk)
    sop.delete()
    messages.success(request, f"SOP '{sop.title}' deleted successfully.")
    return redirect('sop_list')


@login_required
def general_document_list(request):
    search_query = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '').strip()

    documents = GeneralDocument.objects.all().order_by('-uploaded_at')
    if search_query:
        documents = documents.filter(title__icontains=search_query)
    if selected_category:
        documents = documents.filter(category=selected_category)

    categories = GeneralDocument.objects.values_list('category', flat=True).distinct()
    paginator = Paginator(documents, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'documents': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': selected_category,
        'search_query': search_query,
        'current_page': 'documents',
    }
    return render(request, 'documents/general_list.html', context)


@login_required
def upload_general_document(request):
    if request.method == 'POST':
        form = GeneralDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "File added successfully.")
            return redirect('general_document_list')
        messages.error(request, "There was a problem uploading the document.")
    else:
        form = GeneralDocumentForm()
    return render(request, 'documents/upload_general.html', {'form': form, 'current_page': 'documents'})


@login_required
def delete_document(request, pk):
    doc = get_object_or_404(GeneralDocument, pk=pk)
    if request.method == 'POST':
        doc.delete()
        messages.success(request, "Document deleted successfully.")
    return redirect('general_document_list')
