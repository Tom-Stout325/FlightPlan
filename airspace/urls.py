from django.urls import path
from django.db.models import Sum
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


from .views import (
    airspace_helper,
    AirspacePortalView,
    WaiverPlanningListView,
    waiver_planning_new,
    waiver_planning_delete,
    waiver_application_overview,
    waiver_application_description,
    WaiverEquipmentChecklistView,

    conops_overview,
    conops_section_edit,
    
)

app_name = "airspace"

urlpatterns = [
    path("portal/", AirspacePortalView.as_view(), name="airspace_portal"),
    path("guide", airspace_helper, name="airspace_guide"),
    path("waiver/planning/new/", waiver_planning_new, name="waiver_planning_new"),
    path("waiver/equipment-checklist/", WaiverEquipmentChecklistView.as_view(), name="waiver_equipment_checklist",),

    path("waiver/planning/", WaiverPlanningListView.as_view(), name="waiver_planning_list",),
    path("waiver/planning/<int:planning_id>/application/", waiver_application_overview, name="waiver_application_overview",),
    path("waiver/application/<int:pk>/description/", waiver_application_description, name="waiver_application_description",),

    path("waiver/planning/<int:pk>/delete/", waiver_planning_delete, name="waiver_planning_delete",),

path("waiver/application/<int:pk>/conops/",conops_overview,name="conops_overview",),
path("waiver/application/<int:pk>/conops/<slug:section_key>/", conops_section_edit, name="conops_section_edit",),

]



