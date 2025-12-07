from django.db.models import Sum
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView, TemplateView
from django.urls import reverse 

from .forms import AirspaceWaiverForm, WaiverPlanningForm
from .models import AirspaceWaiver, WaiverPlanning
from .services import generate_conops_text


from flightlogs.models import FlightLog 
from equipment.models import Equipment




class AirspacePortalView(LoginRequiredMixin, TemplateView):
    template_name = "airspace/airspace_portal.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # ---- Flight stats ----
        # Use the actual field name from your FlightLog model: pilot_in_command
        # If pilot_in_command is a ForeignKey to User, this will work directly.
        # If it's a CharField, it will just result in 0 unless the names match,
        # which is still safe.
        flights = FlightLog.objects.filter(pilot_in_command=user)

        ctx["total_flights"] = flights.count()

        # Sum the air_time DurationField safely
        total_flight_time = flights.aggregate(total=Sum("air_time"))["total"]
        ctx["total_flight_time"] = total_flight_time

        # Count active drones (no user filter for now to avoid field-name mismatches)
        ctx["active_drones"] = Equipment.objects.filter(
            equipment_type="Drone",
            active=True,
        ).count()

        # ---- Waiver stats ----
        waivers = AirspaceWaiver.objects.filter(user=user)
        ctx["total_waivers"] = waivers.count()
        ctx["waivers_with_conops"] = waivers.exclude(
            conops_text__isnull=True
        ).exclude(conops_text="").count()
        ctx["upcoming_waivers"] = waivers.filter(
            end_date__gte=timezone.now().date()
        ).count()

        return ctx



@login_required
def airspace_waiver(request):
    """
    Simple landing/helper page for the airspace waiver helper.
    """
    return render(request, "airspace/airspace_waiver.html")




@login_required
def airspace_waiver_form(request):
    """
    Step 2: FAA waiver form.

    If a planning entry was created first, we accept a planning_id via
    querystring or POST and link that planning record to the newly-
    created waiver after successful save.

    After submission, the user is sent back to the Waiver List.
    """
    planning_id = request.GET.get("planning_id") or request.POST.get("planning_id")
    planning = None
    if planning_id:
        try:
            planning = WaiverPlanning.objects.get(pk=planning_id, user=request.user)
        except WaiverPlanning.DoesNotExist:
            planning = None

    if request.method == "POST":
        form = AirspaceWaiverForm(request.POST)
        if form.is_valid():
            waiver = form.save(commit=False)
            waiver.user = request.user
            waiver.save()  # computes decimal coords in model.save()

            # Attach planning to this waiver, if present and not already linked
            if planning and planning.waiver_id is None:
                planning.waiver = waiver
                planning.save(update_fields=["waiver"])

            messages.success(
                request,
                "Waiver draft saved. You can now generate a CONOPS from this data.",
            )
            return redirect("airspace:waiver_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AirspaceWaiverForm()

    context = {
        "form": form,
        "planning_id": planning_id,
    }
    return render(request, "airspace/waiver_form.html", context)




@login_required
def airspace_waiver_edit(request, pk):
    """
    Edit an existing AirspaceWaiver.
    """
    waiver = get_object_or_404(AirspaceWaiver, pk=pk, user=request.user)

    if request.method == "POST":
        form = AirspaceWaiverForm(request.POST, instance=waiver)
        if form.is_valid():
            waiver = form.save()
            messages.success(request, "Waiver updated successfully.")
            return redirect("airspace:waiver_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AirspaceWaiverForm(instance=waiver)

    context = {
        "form": form,
        "waiver": waiver,
        "lat_decimal": waiver.lat_decimal,
        "lon_decimal": waiver.lon_decimal,
    }
    return render(request, "airspace/waiver_form.html", context)





@login_required
def waiver_conops_view(request, pk):
    """
    Display a single waiver and allow generating / regenerating CONOPS text.
    """
    waiver = get_object_or_404(AirspaceWaiver, pk=pk, user=request.user)

    if request.method == "POST":
        try:
            conops = generate_conops_text(waiver)
            waiver.conops_text = conops
            waiver.conops_generated_at = timezone.now()
            waiver.save(update_fields=["conops_text", "conops_generated_at"])
            messages.success(request, "CONOPS generated successfully.")
            return redirect("airspace:waiver_conops", pk=waiver.pk)
        except Exception as e:
            messages.error(
                request,
                f"Something went wrong while generating the CONOPS: {e}",
            )

    context = {
        "waiver": waiver,
    }
    return render(request, "airspace/waiver_conops.html", context)




class ConopsListView(LoginRequiredMixin, ListView):
    """
    Shows only waivers that already have CONOPS text.
    """
    model = AirspaceWaiver
    template_name = "airspace/conops_list.html"
    context_object_name = "waivers"
    paginate_by = 20  # optional

    def get_queryset(self):
        return (
            AirspaceWaiver.objects.filter(user=self.request.user)
            .exclude(conops_text__isnull=True)
            .exclude(conops_text__exact="")
            .order_by("-conops_generated_at", "-created_at")
        )




class WaiverListView(LoginRequiredMixin, ListView):
    """
    Shows all waivers for the logged-in user, regardless of CONOPS status.
    """
    model = AirspaceWaiver
    template_name = "airspace/waiver_list.html"
    context_object_name = "waivers"
    paginate_by = 20  # tweak or remove as you prefer

    def get_queryset(self):
        return (
            AirspaceWaiver.objects.filter(user=self.request.user)
            .order_by("-created_at")
        )




@login_required
def waiver_planning_new(request):
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
            url = reverse("airspace:waiver_form")
            return redirect(f"{url}?planning_id={planning.pk}")
    else:
        form = WaiverPlanningForm(user=request.user)

    # Build lightweight data for JS auto-fill (pilots)
    pilot_qs = form.fields["pilot_profile"].queryset
    pilot_profile_data = []
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

    # Build lightweight data for JS auto-fill (aircraft -> safety features)
    aircraft_qs = form.fields["aircraft"].queryset.select_related("drone_safety_profile")
    drone_safety_data = []
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
        "planning_mode": "new",
        "pilot_profile_data": pilot_profile_data,
        "drone_safety_data": drone_safety_data,
    }
    return render(request, "airspace/waiver_planning.html", context)






@login_required
def waiver_planning_edit(request, pk):
    waiver = get_object_or_404(AirspaceWaiver, pk=pk, user=request.user)
    planning, created = WaiverPlanning.objects.get_or_create(
        waiver=waiver,
        defaults={"user": request.user},
    )

    if request.method == "POST":
        form = WaiverPlanningForm(request.POST, instance=planning, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Planning details updated.")
            return redirect("airspace:waiver_edit", pk=waiver.pk)
    else:
        form = WaiverPlanningForm(instance=planning, user=request.user)

    pilot_qs = form.fields["pilot_profile"].queryset
    pilot_profile_data = []
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

    # Aircraft -> safety features data
    aircraft_qs = form.fields["aircraft"].queryset.select_related("drone_safety_profile")
    drone_safety_data = []
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
        "planning_mode": "edit",
        "waiver": waiver,
        "pilot_profile_data": pilot_profile_data,
        "drone_safety_data": drone_safety_data,
    }
    return render(request, "airspace/waiver_planning.html", context)
