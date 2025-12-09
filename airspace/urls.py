from django.urls import path
from .views import (
    AirspacePortalView,
    waiver_planning_new,
    airspace_waiver_form,
    waiver_conops_view,
    ConopsListView,
    WaiverListView,
    airspace_waiver_edit,
    airspace_waiver,
    AirspaceWaiverDraftWizard,
    
    # waiver_planning_edit,
)

app_name = "airspace"

urlpatterns = [
    path("", AirspacePortalView.as_view(), name="portal_home"),

    # Helper waiver route
    path("waiver/helper/", airspace_waiver, name="waiver"),

    # NEW 3-step Draft Wizard
    path(
        "waiver/draft/new/",
        AirspaceWaiverDraftWizard.as_view(),
        name="waiver_draft_new",
    ),

    # Planning (pre-wizard)
    path("waiver/planning/new/", waiver_planning_new, name="waiver_planning_new"),

    # Old single-page waiver form (still available if you need it)
    path("waiver/form/", airspace_waiver_form, name="waiver_form"),

    # CONOPS & Waivers
    path("waiver/<int:pk>/conops/", waiver_conops_view, name="waiver_conops"),
    path("conops/", ConopsListView.as_view(), name="conops_list"),
    path("waivers/", WaiverListView.as_view(), name="waiver_list"),
    path("waiver/<int:pk>/edit/", airspace_waiver_edit, name="waiver_edit"),
    
    
    # path("waiver/<int:pk>/planning/", waiver_planning_edit, name="waiver_planning_edit"),
]
