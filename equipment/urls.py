# equipment/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views


app_name = "equipment"

urlpatterns = [
    path("equipment/", views.equipment_list, name="equipment_list"),
    path("equipment/create/", views.equipment_create, name="equipment_create"),
    path("equipment/pdf/", views.equipment_pdf, name="equipment_pdf"),
    path("equipment/<uuid:pk>/edit/", views.equipment_edit, name="equipment_edit"),
    path("equipment/<uuid:pk>/delete/", views.equipment_delete, name="equipment_delete"),
    path("equipment/<uuid:pk>/pdf/", views.equipment_pdf_single, name="equipment_pdf_single"),
    path("equipment/export/csv/", views.export_equipment_csv, name="export_equipment_csv"),
    path("api/drone-suggest/", views.drone_profile_suggest_view, name="drone_profile_suggest",),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
