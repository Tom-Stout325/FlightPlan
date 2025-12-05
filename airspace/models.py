from decimal import Decimal  # optional, you can remove if not used elsewhere

from django.conf import settings
from django.db import models

from .utils import dms_to_decimal
from equipment.models import Equipment


class AirspaceWaiver(models.Model):
    # ----- Choice sets -----
    TIMEFRAME_CHOICES = [
        ("sunrise_noon", "Sunrise to Noon"),
        ("noon_4pm", "Noon to 4 PM"),
        ("4pm_sunset", "4 PM to Sunset"),
        ("night", "Night"),
    ]

    FREQUENCY_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("biweekly", "Bi-weekly"),
        ("monthly", "Monthly"),
    ]

    AIRSPACE_CLASS_CHOICES = [
        ("B", "Class B"),
        ("C", "Class C"),
        ("D", "Class D"),
        ("E", "Class E"),
        ("G", "Class G"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("final", "Final"),
    ]

    # ----- Ownership -----
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="airspace_waivers",
    )

    # ----- 1. Operation overview -----
    operation_title = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    timeframe = models.CharField(max_length=20, choices=TIMEFRAME_CHOICES)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    # we enforce timezone choices in the form; model just stores the string
    local_timezone = models.CharField(max_length=64)

    # ----- 2. Location & airspace -----
    proposed_location = models.TextField()
    max_agl = models.PositiveIntegerField(help_text="Maximum altitude AGL in feet")

    # Latitude (DMS)
    lat_degrees = models.PositiveSmallIntegerField()
    lat_minutes = models.PositiveSmallIntegerField()
    lat_seconds = models.DecimalField(max_digits=7, decimal_places=4)
    lat_direction = models.CharField(max_length=1, choices=[("N", "N"), ("S", "S")])

    # Longitude (DMS)
    lon_degrees = models.PositiveSmallIntegerField()
    lon_minutes = models.PositiveSmallIntegerField()
    lon_seconds = models.DecimalField(max_digits=7, decimal_places=4)
    lon_direction = models.CharField(max_length=1, choices=[("E", "E"), ("W", "W")])

    radius_nm = models.DecimalField(max_digits=4, decimal_places=2)
    nearest_airport = models.CharField(max_length=10)
    airspace_class = models.CharField(max_length=1, choices=AIRSPACE_CLASS_CHOICES)

    # Decimal coordinates (auto-derived)
    lat_decimal = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    lon_decimal = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    # ----- 3. Description & existing waivers -----
    short_description = models.TextField()
    has_related_waiver = models.BooleanField(default=False)
    related_waiver_details = models.TextField(blank=True)

    # ----- Aircraft selection -----
    aircraft = models.ForeignKey(
        Equipment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="airspace_waivers",
        help_text="Select a drone from your equipment list (optional).",
    )
    aircraft_custom = models.CharField(
        max_length=255,
        blank=True,
        help_text="If not in the list, describe the aircraft here.",
    )

    # ----- CONOPS output -----
    conops_text = models.TextField(blank=True)
    conops_generated_at = models.DateTimeField(null=True, blank=True)

    # ----- Meta / bookkeeping -----
    status = models.CharField(
        max_length=20,
        default="draft",
        choices=STATUS_CHOICES,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ----- Helpers -----
    def update_decimal_coords(self):
        """
        Recalculate decimal lat/lon from DMS + direction.
        Called automatically in save().
        """
        self.lat_decimal = dms_to_decimal(
            self.lat_degrees,
            self.lat_minutes,
            self.lat_seconds,
            self.lat_direction,
        )
        self.lon_decimal = dms_to_decimal(
            self.lon_degrees,
            self.lon_minutes,
            self.lon_seconds,
            self.lon_direction,
        )

    def save(self, *args, **kwargs):
        # Always keep decimals in sync before saving
        self.update_decimal_coords()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.operation_title} ({self.user})"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Airspace Waiver"
        verbose_name_plural = "Airspace Waivers"


class WaiverPlanning(models.Model):
    """
    Holds planning details that are not part of the FAA waiver form itself
    but are critical for CONOPS: aircraft, pilot, hours, launch location,
    and safety features.
    """

    waiver = models.OneToOneField(
        "airspace.AirspaceWaiver",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="planning",
        help_text="Linked waiver. May be null until the FAA waiver form is submitted.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="waiver_planning_entries",
    )

    # Aircraft
    aircraft = models.ForeignKey(
        Equipment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="waiver_planning_entries",
        limit_choices_to={"equipment_type": "Drone"},
        help_text="Select a drone from your equipment list (optional).",
    )
    aircraft_manual = models.CharField(
        max_length=255,
        blank=True,
        help_text="If needed, manually describe any additional aircraft types.",
    )

    # Pilot
    pilot_profile = models.ForeignKey(
        "pilot.PilotProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="waiver_planning_entries",
        help_text="Pilot selected from your Pilot Profile app (optional).",
    )
    pilot_name_manual = models.CharField(
        max_length=255,
        blank=True,
        help_text="Manual pilot name override, if not using a profile.",
    )
    pilot_cert_manual = models.CharField(
        max_length=255,
        blank=True,
        help_text="Manual Part 107 certificate number, if not using a profile.",
    )
    pilot_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Approximate total UAS flight hours for this pilot.",
    )

    # Launch location & safety features
    launch_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Typical launch location or staging area for this waiver.",
    )
    safety_features_notes = models.TextField(
        blank=True,
        help_text="Key safety features, redundancies, or geofencing used for this operation.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Convenience helpers for CONOPS
    def pilot_display_name(self) -> str:
        if self.pilot_name_manual:
            return self.pilot_name_manual
        if self.pilot_profile and self.pilot_profile.user:
            u = self.pilot_profile.user
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return ""

    def pilot_cert_display(self) -> str:
        if self.pilot_cert_manual:
            return self.pilot_cert_manual
        if self.pilot_profile and self.pilot_profile.license_number:
            return self.pilot_profile.license_number
        return ""

    def aircraft_display(self) -> str:
        if self.aircraft:
            return str(self.aircraft)
        if self.aircraft_manual:
            return self.aircraft_manual
        return ""

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Waiver Planning Entry"
        verbose_name_plural = "Waiver Planning Entries"

    def __str__(self) -> str:
        if self.waiver:
            return f"Planning for {self.waiver.operation_title}"
        return f"Planning draft by {self.user}"
