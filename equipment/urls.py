# equipment/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from django.contrib.admin.views.decorators import staff_member_required
from . import views

app_name = "equipment"

urlpatterns = [
    # ------------------------------------------------------------
    # Equipment Inventory
    # ------------------------------------------------------------
    path("equipment/", views.equipment_list, name="equipment_list"),
    path("equipment/create/", views.equipment_create, name="equipment_create"),
    path("equipment/<uuid:pk>/edit/", views.equipment_edit, name="equipment_edit"),
    path("equipment/<uuid:pk>/delete/", views.equipment_delete, name="equipment_delete"),

    # Exports
    path("equipment/pdf/", views.equipment_pdf, name="equipment_pdf"),
    path("equipment/<uuid:pk>/pdf/", views.equipment_pdf_single, name="equipment_pdf_single"),
    path("equipment/export/csv/", views.export_equipment_csv, name="export_equipment_csv"),

    # ------------------------------------------------------------
    # Drone Safety Profiles
    # ------------------------------------------------------------
    path("drone-profiles/", views.drone_safety_profile_list, name="drone_safety_profile_list"),
    
    path("drone-profiles/create/", staff_member_required(views.drone_safety_profile_create), name="drone_safety_profile_create"),
    path("drone-profiles/<int:pk>/edit/", staff_member_required(views.drone_safety_profile_edit), name="drone_safety_profile_edit"),
    path("drone-profiles/<int:pk>/delete/", staff_member_required(views.drone_safety_profile_delete), name="drone_safety_profile_delete"),

    # ------------------------------------------------------------
    # API
    # ------------------------------------------------------------
    path("api/drone-suggest/", views.drone_profile_suggest, name="drone_profile_suggest"),
]

if settings.DEBUG and not getattr(settings, "USE_S3", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


