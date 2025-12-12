from django.contrib import messages
import logging
logger = logging.getLogger(__name__)

from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView, TemplateView
from django.urls import reverse
from formtools.wizard.views import SessionWizardView
from django.http import HttpResponseRedirect


from .services import generate_conops_text
from .utils import dms_to_decimal 
from .utils import generate_short_description
from flightlogs.models import FlightLog
from equipment.models import Equipment

from .utils import decimal_to_dms

from pilot.models import PilotProfile
from equipment.models import Equipment

from .models import (
        WaiverPlanning, 
        WaiverApplication, 
        WaiverPlanning
)

from .forms import (
        WaiverPlanningForm,
        WaiverApplicationDescriptionForm,

)





def decimal_to_dms(value, is_lat=True):
    """
    Convert a signed decimal degree value (e.g. 39.811556) into a dict:
    {
      "deg": 39,
      "min": 48,
      "sec": 41.6,
      "dir": "N"
    }
    is_lat=True -> N/S, is_lat=False -> E/W
    """
    if value is None:
        return None

    # Ensure we can do math on it (handles Decimal)
    val = float(value)

    if is_lat:
        pos_dir, neg_dir = "N", "S"
    else:
        pos_dir, neg_dir = "E", "W"

    direction = pos_dir if val >= 0 else neg_dir
    val = abs(val)

    deg = int(val)
    minutes_full = (val - deg) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60, 1)

    return {
        "deg": deg,
        "min": minutes,
        "sec": seconds,
        "dir": direction,
    }






class WaiverEquipmentChecklistView(LoginRequiredMixin, TemplateView):
    """
    Standalone printable checklist of required on-site equipment
    for waiver / ops planning. Does not store data – purely a guide.
    """
    template_name = "airspace/waiver_equipment_checklist.html"



class AirspacePortalView(LoginRequiredMixin, TemplateView):
    template_name = "airspace/airspace_portal.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # ---- Flight stats ----
        full_name = f"{user.first_name} {user.last_name}".strip()
        flights = FlightLog.objects.filter(pilot_in_command__iexact=full_name)

        ctx["total_flights"] = flights.count()

        # Sum the air_time DurationField safely
        total_flight_time = flights.aggregate(total=Sum("air_time"))["total"]
        ctx["total_flight_time"] = total_flight_time  # can be None if no flights

        # ---- Equipment stats ----
        ctx["active_drones"] = Equipment.objects.filter(
            equipment_type="Drone",
            active=True,
        ).count()

        # ---- Waiver stats (placeholder for now) ----
        ctx["total_waivers"] = 0
        ctx["waivers_with_conops"] = 0
        ctx["upcoming_waivers"] = 0

        return ctx







@login_required
def airspace_helper(request):
    return render(request, "airspace/airspace_guide.html")






@login_required
def waiver_planning_new(request):
    planning_id = request.GET.get("planning_id")
    planning = None

    if planning_id:
        planning = get_object_or_404(
            WaiverPlanning,
            id=planning_id,
            user=request.user,
        )

    if request.method == "POST":
        form = WaiverPlanningForm(request.POST, user=request.user, instance=planning)
        if form.is_valid():
            planning = form.save(commit=False)
            planning.user = request.user
            planning.save()
            form.save_m2m()
            return redirect(
                "airspace:waiver_application_overview",
                planning_id=planning.id,
            )
    else:
        form = WaiverPlanningForm(user=request.user, instance=planning)

    # ----------------------------------------
    # Pilot profile data for JS auto-fill
    # ----------------------------------------
    pilot_profile_data = []
    pilot_field = form.fields.get("pilot_profile")

    if pilot_field is not None:
        pilot_qs = pilot_field.queryset
    else:
        pilot_qs = PilotProfile.objects.none()

    for profile in pilot_qs.select_related("user"):
        try:
            total_seconds = profile.flight_time_total()  # your helper
        except TypeError:
            total_seconds = 0
        flight_hours = round(total_seconds / 3600, 1) if total_seconds else 0

        pilot_profile_data.append(
            {
                "id": profile.id,
                "license_number": profile.license_number or "",
                "flight_hours": flight_hours,
            }
        )

    # ----------------------------------------
    # Drone safety data for JS auto-fill
    # ----------------------------------------
    drone_safety_data = []
    aircraft_field = form.fields.get("aircraft")

    if aircraft_field is not None:
        # This queryset is Equipment objects limited to equipment_type="Drone"
        equipment_qs = aircraft_field.queryset.select_related("drone_safety_profile")

        for equip in equipment_qs:
            profile = getattr(equip, "drone_safety_profile", None)
            safety_text = profile.safety_features if profile else ""
            drone_safety_data.append(
                {
                    # IMPORTANT: id must match the <select> value -> Equipment.pk
                    "id": equip.id,
                    "safety_features": safety_text or "",
                }
            )

    context = {
        "form": form,
        "planning": planning,
        "planning_mode": "edit" if planning else "new",
        "pilot_profile_data": pilot_profile_data,
        "drone_safety_data": drone_safety_data,
    }
    return render(request, "airspace/waiver_planning_form.html", context)






class WaiverPlanningDescriptionForm(WaiverPlanningForm):
    """
    Slimmed-down version of WaiverPlanningForm used on the
    Description page. Re-uses all widgets/choices/__init__
    logic from WaiverPlanningForm but only exposes the fields
    that feed the Description of Operations.
    """

    class Meta(WaiverPlanningForm.Meta):
        fields = [
            # Aircraft / pilot
            "aircraft",
            "aircraft_manual",
            "pilot_profile",
            "pilot_flight_hours",

            # Waivers
            "operates_under_10739",
            "oop_waiver_document",
            "oop_waiver_number",
            "operates_under_107145",
            "mv_waiver_document",
            "mv_waiver_number",

            # Purpose of operations
            "purpose_operations",
            "purpose_operations_details",

            # Location / venue
            "venue_name",
            "street_address",
            "location_city",
            "location_state",
            "zip_code",
            "launch_location",

            # Safety / insurance
            "uses_drone_detection",
            "uses_flight_tracking",
            "has_visual_observer",
            "insurance_provider",
            "insurance_coverage_limit",
            "safety_features_notes",

            # Operational profile
            "aircraft_count",
            "flight_duration",
            "flights_per_day",
            "ground_environment",
            "estimated_crowd_size",
            "prepared_procedures",
        ]






@login_required
def waiver_application_overview(request, planning_id):
    """
    Step 1.5 – Overview of the FAA waiver application, with data coming
    from WaiverPlanning. This view also ensures a WaiverApplication object
    exists for this planning entry.
    """
    planning = get_object_or_404(
        WaiverPlanning,
        id=planning_id,
        user=request.user,
    )

    # Ensure there is an application object tied to this planning entry
    application, created = WaiverApplication.objects.get_or_create(
        planning=planning,
        user=request.user,
    )

    # ----- Build timeframe label list from codes -----
    timeframe_labels = []
    if planning.timeframe:
        code_to_label = dict(WaiverPlanning.TIMEFRAME_CHOICES)
        for code in planning.timeframe:
            label = code_to_label.get(code, code)
            timeframe_labels.append(label)

    # ----- Convert stored decimal coords back to DMS for display -----
    lat_dms = decimal_to_dms(planning.location_latitude, is_lat=True)
    lon_dms = decimal_to_dms(planning.location_longitude, is_lat=False)

    if request.method == "POST":
        if "back" in request.POST:
            return redirect("airspace:waiver_planning_list")
        if "continue" in request.POST:
            return redirect(
                "airspace:waiver_application_description",
                pk=application.pk,
            )

    context = {
        "planning": planning,
        "application": application,
        "timeframe_labels": timeframe_labels,
        "lat_dms": lat_dms,
        "lon_dms": lon_dms,
    }
    return render(request, "airspace/waiver_application_overview.html", context)






@login_required
def waiver_application_description(request, pk):
    """
    Step 2: Description builder page.
    Shows key planning inputs (editable) above the Description textarea,
    plus buttons to save changes or regenerate the description.
    """
    application = get_object_or_404(
        WaiverApplication,
        pk=pk,
        user=request.user,
    )
    planning = application.planning

    if request.method == "POST":
        planning_form = WaiverPlanningDescriptionForm(
            request.POST,
            instance=planning,
            user=request.user,
        )
        app_form = WaiverApplicationDescriptionForm(
            request.POST,
            instance=application,
        )

        if planning_form.is_valid() and app_form.is_valid():
            # Save any edits to the planning data
            planning = planning_form.save()

            # Save / update description
            application = app_form.save(commit=False)

            if "generate" in request.POST:
                # Placeholder generator — later we’ll drop in OpenAI logic here
                application.description = (
                    "Description of Operations (draft)\n\n"
                    f"Operation: {planning.operation_title}\n"
                    f"Location: {planning.venue_name}, "
                    f"{planning.location_city}, {planning.location_state} {planning.zip_code}\n"
                    f"Dates: {planning.start_date} to "
                    f"{planning.end_date or planning.start_date}\n\n"
                    "<<< TODO: Replace this stub with AI-generated narrative "
                    "using the planning details above. >>>"
                )

            application.save()

            # Re-bind fresh instances so the template shows updated values
            planning = application.planning
            planning_form = WaiverPlanningDescriptionForm(
                instance=planning,
                user=request.user,
            )
            app_form = WaiverApplicationDescriptionForm(instance=application)

    else:
        planning_form = WaiverPlanningDescriptionForm(
            instance=planning,
            user=request.user,
        )
        app_form = WaiverApplicationDescriptionForm(instance=application)

    context = {
        "planning": planning,
        "application": application,
        "planning_form": planning_form,
        "app_form": app_form,
    }
    return render(
        request,
        "airspace/waiver_application_description.html",
        context,
    )









class WaiverPlanningListView(LoginRequiredMixin, ListView):
    """
    Lists all WaiverPlanning entries for the logged-in user.
    """
    model = WaiverPlanning
    template_name = "airspace/waiver_planning_list.html"
    context_object_name = "planning_list"
    paginate_by = 20

    def get_queryset(self):
        return (
            WaiverPlanning.objects
            .filter(user=self.request.user)
            .order_by("-created_at")
        )




@login_required
def waiver_planning_delete(request, pk):
    """
    Delete a WaiverPlanning entry (user-restricted).
    """
    planning = get_object_or_404(
        WaiverPlanning,
        pk=pk,
        user=request.user, 
    )

    if request.method == "POST":
        planning.delete()
        messages.success(request, "Waiver planning entry deleted.")
        return redirect("airspace:waiver_planning_list")

    # Optional confirmation page:
    return render(request, "airspace/waiver_planning_confirm_delete.html", {
        "planning": planning
    })
