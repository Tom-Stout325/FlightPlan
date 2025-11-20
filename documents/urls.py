# documents/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views
from .forms import (
    EventDetailsForm,
    GeneralInfoForm,
    EquipmentDetailsForm,
    EnvironmentalConditionsForm,
    WitnessForm,
    ActionTakenForm,
    FollowUpForm,
)

app_name = "documents"

# Incident report wizard steps
wizard_forms = [
    ("general_info", GeneralInfoForm),
    ("event_details", EventDetailsForm),
    ("equipment_details", EquipmentDetailsForm),
    ("environmental_conditions", EnvironmentalConditionsForm),
    ("witness", WitnessForm),
    ("action_taken", ActionTakenForm),
    ("follow_up", FollowUpForm),
]

urlpatterns = [
    # Incident reporting
    path(
        "incident-reporting/",
        views.incident_reporting_system,
        name="incident_reporting_system",
    ),
    path(
        "report/new/",
        views.IncidentReportWizard.as_view(wizard_forms),
        name="submit_incident_report",
    ),
    path(
        "report/success/",
        views.incident_report_success,
        name="incident_report_success",
    ),
    path(
        "report/pdf/<int:pk>/",
        views.incident_report_pdf,
        name="incident_report_pdf",
    ),
    path(
        "incidents/",
        views.incident_report_list,
        name="incident_report_list",
    ),
    path(
        "incidents/<int:pk>/",
        views.incident_report_detail,
        name="incident_report_detail",
    ),

    # SOPs & General Documents
    path("sops/", views.sop_list, name="sop_list"),
    path("sops/upload/", views.sop_upload, name="sop_upload"),
    path("sops/delete/<int:pk>/", views.delete_sop, name="delete_sop"),

    path("documents/", views.general_document_list, name="general_document_list"),
    path(
        "documents/upload/",
        views.upload_general_document,
        name="upload_general_document",
    ),
    path(
        "documents/delete/<int:pk>/",
        views.delete_document,
        name="delete_document",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
