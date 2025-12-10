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


from .services import generate_conops_text
from .utils import dms_to_decimal 
from .utils import generate_short_description
from flightlogs.models import FlightLog
from equipment.models import Equipment



from .forms import (
    WaiverPlanningForm,
 
)





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
    """
    Create a new waiver planning entry (single-page planning form).
    Captures operation, aircraft, pilot, location, and safety details that
    will feed into the FAA waiver application and Description of Operations.
    """
    planning = None

    if request.method == "POST":
        form = WaiverPlanningForm(request.POST, user=request.user)
        if form.is_valid():
            planning = form.save(commit=False)
            planning.user = request.user
            planning.save()

            messages.success(
                request,
                "Planning details saved. Continue to the FAA waiver application.",
            )

            # For now, keep redirecting to the existing waiver form view.
            # Later we can point this to the new waiver_application_new view.
            url = reverse("airspace:waiver_form")
            return redirect(f"{url}?planning_id={planning.pk}")
    else:
        form = WaiverPlanningForm(user=request.user)

    # -------------------------
    # Pilot profile auto-fill data
    # -------------------------
    pilot_profile_data = []
    pilot_field = form.fields.get("pilot_profile")
    if pilot_field is not None:
        pilot_qs = pilot_field.queryset
        for p in pilot_qs:
            total_seconds = p.flight_time_total() or 0
            hours_value = round(total_seconds / 3600.0, 1)
            pilot_profile_data.append(
                {
                    "id": p.id,
                    "first_name": p.user.first_name,
                    "last_name": p.user.last_name,
                    "license_number": getattr(p, "license_number", "") or "",
                    "flight_hours": hours_value,
                }
            )

    # -------------------------
    # Drone safety auto-fill data
    # -------------------------
    drone_safety_data = []
    aircraft_field = form.fields.get("aircraft")
    if aircraft_field is not None:
        aircraft_qs = aircraft_field.queryset.select_related("drone_safety_profile")
        for eq in aircraft_qs:
            profile = getattr(eq, "drone_safety_profile", None)
            if profile and profile.safety_features:
                drone_safety_data.append(
                    {
                        "id": str(eq.pk),
                        "safety_features": profile.safety_features,
                    }
                )

    context = {
        "form": form,
        "planning": planning,          # used by the "Start Waiver Draft" button
        "planning_mode": "new",
        "pilot_profile_data": pilot_profile_data,
        "drone_safety_data": drone_safety_data,
    }
    return render(request, "airspace/waiver_planning_new.html", context)
























