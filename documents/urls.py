from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.documents, name="documents_portal"),

    # Incidents
    path("incidents/", views.incident_reporting_system, name="incident_reporting_system"),
    path("incidents/new/", views.IncidentReportWizard.as_view(), name="incident_report_wizard"),
    path("incidents/<int:pk>/", views.incident_report_detail, name="incident_report_detail"),
    path("incidents/<int:pk>/pdf/", views.incident_report_pdf, name="incident_report_pdf"),

    # SOPs
    path("sops/", views.sop_list, name="sop_list"),
    path("sops/upload/", views.sop_upload, name="sop_upload"),
    path("sops/<int:pk>/delete/", views.delete_sop, name="delete_sop"),

    # General documents
    path("documents/", views.general_document_list, name="general_document_list"),
    path("documents/upload/", views.upload_general_document, name="upload_general_document"),
    path("documents/<int:pk>/delete/", views.delete_document, name="delete_document"),
]

if settings.DEBUG and not getattr(settings, "USE_S3", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
