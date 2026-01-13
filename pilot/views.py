# pilot/views.py

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldError
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from flightlogs.models import FlightLog

from .forms import PilotProfileForm, TrainingForm
from .models import PilotProfile, Training


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _get_pilot_profile(user):
    """
    Enforce user-scoped access to the pilot profile.
    """
    return get_object_or_404(PilotProfile, user=user)


def _flightlogs_for_user(user):
    """
    Best-effort user scoping for FlightLog without assuming the exact schema.
    Prefers an explicit user FK if it exists; falls back to matching pilot name.
    """
    # Try the most secure / direct approach first
    try:
        return FlightLog.objects.filter(user=user)
    except FieldError:
        pass

    # Fallback: match "pilot_in_command" to user's full name (your PilotProfile model uses this too)
    full_name = f"{user.first_name} {user.last_name}".strip()
    if full_name:
        try:
            return FlightLog.objects.filter(pilot_in_command__iexact=full_name)
        except FieldError:
            return FlightLog.objects.none()

    return FlightLog.objects.none()


# -----------------------------------------------------------------------------
# Pilot Profile
# -----------------------------------------------------------------------------

@login_required
def profile(request):
    profile = _get_pilot_profile(request.user)

    logs = _flightlogs_for_user(request.user)

    # Aggregate stats (defensive if fields are missing)
    # These are best-effort and won't error if a field doesn't exist.
    totals = {
        "flight_count": logs.count(),
        "total_distance_ft": None,
        "total_air_time": None,
        "total_media_count": None,
    }

    try:
        totals["total_distance_ft"] = logs.aggregate(
            v=Coalesce(Sum("max_distance_ft"), 0)
        )["v"]
    except FieldError:
        pass

    try:
        totals["total_air_time"] = logs.aggregate(
            v=Coalesce(Sum("air_time"), 0)
        )["v"]
    except FieldError:
        pass

    # Optional: if you store media counts in fields
    try:
        totals["total_media_count"] = logs.aggregate(
            v=Coalesce(Sum("media_count"), 0)
        )["v"]
    except FieldError:
        pass

    # “Top” flights – scoped to the user logs queryset
    highest_altitude_flight = None
    fastest_speed_flight = None
    longest_flight = None

    try:
        highest_altitude_flight = logs.order_by("-max_altitude_ft").first()
    except FieldError:
        pass

    try:
        fastest_speed_flight = logs.order_by("-max_speed_mph").first()
    except FieldError:
        pass

    try:
        longest_flight = logs.order_by("-max_distance_ft").first()
    except FieldError:
        pass

    trainings = profile.trainings.all().order_by("-date_completed", "-id")

    context = {
        "profile": profile,
        "trainings": trainings,
        "logs": logs,  # if your template uses it
        "totals": totals,
        "highest_altitude_flight": highest_altitude_flight,
        "fastest_speed_flight": fastest_speed_flight,
        "longest_flight": longest_flight,
    }
    return render(request, "pilot/profile.html", context)


@login_required
def edit_profile(request):
    profile = _get_pilot_profile(request.user)

    if request.method == "POST":
        form = PilotProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Pilot profile updated.")
            return redirect("pilot:profile")
        messages.error(request, "Please correct the errors below.")
    else:
        form = PilotProfileForm(instance=profile)

    return render(request, "pilot/edit_profile.html", {"form": form, "profile": profile})


# -----------------------------------------------------------------------------
# Training CRUD (fully user-scoped)
# -----------------------------------------------------------------------------

@login_required
def training_create(request):
    profile = _get_pilot_profile(request.user)

    if request.method == "POST":
        form = TrainingForm(request.POST, request.FILES)
        if form.is_valid():
            training = form.save(commit=False)

            # 🔒 Hard ownership enforcement (prevents forged POSTs)
            training.pilot = profile

            training.save()
            messages.success(request, "Training record added.")
            return redirect("pilot:profile")
        messages.error(request, "Please correct the errors below.")
    else:
        form = TrainingForm()

    return render(
        request,
        "pilot/training_form.html",
        {
            "form": form,
            "profile": profile,
            "mode": "create",
        },
    )


@login_required
def training_edit(request, pk: int):
    profile = _get_pilot_profile(request.user)

    # 🔒 User-scoped lookup (prevents editing someone else’s record)
    training = get_object_or_404(Training, pk=pk, pilot__user=request.user)

    if request.method == "POST":
        form = TrainingForm(request.POST, request.FILES, instance=training)
        if form.is_valid():
            updated = form.save(commit=False)

            # 🔒 Keep ownership locked even on edit
            updated.pilot = profile

            updated.save()
            messages.success(request, "Training record updated.")
            return redirect("pilot:profile")
        messages.error(request, "Please correct the errors below.")
    else:
        form = TrainingForm(instance=training)

    return render(
        request,
        "pilot/training_form.html",
        {
            "form": form,
            "profile": profile,
            "training": training,
            "mode": "edit",
        },
    )


@login_required
def training_delete(request, pk: int):
    # 🔒 User-scoped lookup (prevents deleting someone else’s record)
    training = get_object_or_404(Training, pk=pk, pilot__user=request.user)

    if request.method == "POST":
        training.delete()
        messages.success(request, "Training record deleted.")
        return redirect("pilot:profile")

    return render(
        request,
        "pilot/training_confirm_delete.html",
        {"training": training},
    )
