from django.urls import path
from django.db.models import Sum
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


from .views import (
    AirspacePortalView,

    airspace_helper,
    waiver_planning_new,


    
)

app_name = "airspace"

urlpatterns = [
    path("portal/", AirspacePortalView.as_view(), name="airspace_portal"),
    path("guide", airspace_helper, name="airspace_guide"),
    path("waiver/planning/new/", waiver_planning_new, name="waiver_planning_new"),


    

]



