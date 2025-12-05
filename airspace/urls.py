from django.urls import path
from .views import (
    AirspacePortalView,
    waiver_planning_new,
    waiver_planning_edit,
    airspace_waiver_form,
    waiver_conops_view,
    ConopsListView,
    WaiverListView,
    airspace_waiver_edit,
    airspace_waiver,
)

app_name = "airspace"

urlpatterns = [
    
    path("", AirspacePortalView.as_view(), name="portal_home"),
    path("waiver/helper/", airspace_waiver, name="waiver"),

    path("waiver/planning/new/", waiver_planning_new, name="waiver_planning_new"),
    path("waiver/<int:pk>/planning/", waiver_planning_edit, name="waiver_planning_edit"),

    path("waiver/form/", airspace_waiver_form, name="waiver_form"),
    path("waiver/<int:pk>/conops/", waiver_conops_view, name="waiver_conops"),
    path("conops/", ConopsListView.as_view(), name="conops_list"),
    path("waivers/", WaiverListView.as_view(), name="waiver_list"),
    path("waiver/<int:pk>/edit/", airspace_waiver_edit, name="waiver_edit"),
    path("waiver/<int:pk>/conops/", waiver_conops_view, name="waiver_conops"),



]
