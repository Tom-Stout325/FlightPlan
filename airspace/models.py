from decimal import Decimal 

from django.conf import settings
from django.db import models

from .utils import dms_to_decimal
from equipment.models import Equipment
from documents.models import GeneralDocument 




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


    OPERATION_ACTIVITY_CHOICES = [
        ("event_filming", "Event filming / broadcast"),
        ("aerial_photography", "Professional aerial photography"),
        ("mapping_survey", "Mapping / survey"),
        ("infrastructure_inspection", "Infrastructure inspection"),
        ("public_safety_support", "Public safety / incident support"),
        ("training", "Training / proficiency flights"),
        ("real_estate_photography", "Real Estate photograpny"),
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
    timeframe = models.CharField(max_length=100, blank=True, help_text="Comma-separated timeframe codes selected for this operation.",)
    operation_activities = models.CharField(max_length=200, blank=True, help_text="Comma-separated activity codes describing what you are doing.",)
    operation_activities_other = models.CharField(max_length=255, blank=True, help_text="Optional free-text description of the operation.",)
    
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    local_timezone = models.CharField(max_length=64)

    # ----- 2. Location & airspace -----
    proposed_location = models.TextField(verbose_name="Location Description", help_text="Venue name, address, GPS coordinates..")
    max_agl = models.PositiveIntegerField(verbose_name="Maximum Altitude (AGL)",help_text="Maximum Altitude AGL in feet")

    # Latitude (DMS)
    lat_degrees = models.PositiveSmallIntegerField(verbose_name="Latitude Degrees")
    lat_minutes = models.PositiveSmallIntegerField(verbose_name="Latitude Minutes")
    lat_seconds = models.DecimalField(verbose_name="Latitude Seconds", max_digits=7, decimal_places=4)
    lat_direction = models.CharField(verbose_name="Latitude Direction", max_length=1, choices=[("N", "N"), ("S", "S")])

    # Longitude (DMS)
    lon_degrees = models.PositiveSmallIntegerField(verbose_name="Longitude Degrees")
    lon_minutes = models.PositiveSmallIntegerField(verbose_name="Longitude Minutes")
    lon_seconds = models.DecimalField(verbose_name="Longitude Seconds", max_digits=7, decimal_places=4)
    lon_direction = models.CharField(verbose_name="Longitude Direction", max_length=1, choices=[("E", "E"), ("W", "W")])

    radius_nm = models.DecimalField(max_digits=4, decimal_places=2)
    nearest_airport = models.CharField(verbose_name="Nearest Airport (ICAO Code)", max_length=10)
    airspace_class = models.CharField(verbose_name="Airspace Class", max_length=1, choices=AIRSPACE_CLASS_CHOICES)

    # Decimal coordinates (auto-derived)
    lat_decimal = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    lon_decimal = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    # ----- 3. Description & existing waivers -----
    short_description = models.TextField(verbose_name="Brief Description of Operations")
    has_related_waiver = models.BooleanField(default=False)
    related_waiver_details = models.CharField(verbose_name="Related Waiver Number", max_length=200, blank=True)

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
        verbose_name="Custom Aircraft",
        help_text="If not listed, enter the Manufacturer and Model.",
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

    def timeframe_codes(self):
        """
        Return the stored timeframe CSV as a list of codes.
        e.g. 'noon_4pm,4pm_sunset' -> ['noon_4pm', '4pm_sunset']
        """
        if not self.timeframe:
            return []
        return [c.strip() for c in self.timeframe.split(",") if c.strip()]

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
    Holds planning details that are not part of the FAA waiver form itself but
    are critical for CONOPS: aircraft, pilot, hours, launch location, and safety features.
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
        "equipment.Equipment",
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
    operates_under_10739 = models.BooleanField(
        default=False,
        help_text=(
            "Check if this operation will be conducted under an approved "
            "14 CFR §107.39 Operations Over People waiver."
        ),
    )

    oop_waiver_document = models.ForeignKey(
        GeneralDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oop_waiver_planning_entries",
        help_text="Select your approved 107.39 waiver from General Documents.",
    )

    oop_waiver_number = models.CharField(
        "Approved 107.39 Waiver Number",
        max_length=100,
        blank=True,
        help_text="Example: 107W-2024-01234",
    )

    # Launch location & safety features
    launch_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Typical launch location or staging area for this waiver.",
    )
    safety_features_notes = models.TextField(
        blank=True,
        help_text=(
            "Key safety features, redundancies, or geofencing used for this operation. "
            "If a drone with a safety profile is selected, this will be auto-filled."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # -------------------------
    # Convenience helpers
    # -------------------------
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

    # -------------------------
    # Safety profile autopopulate
    # -------------------------
    def apply_aircraft_safety_profile(self):
        """
        If an aircraft with a DroneSafetyProfile is selected and safety_features_notes
        is currently empty/whitespace, copy the profile's safety_features in.

        We *don't* overwrite existing notes so you can safely customize them.
        """
        if self.aircraft and not (self.safety_features_notes or "").strip():
            profile = getattr(self.aircraft, "drone_safety_profile", None)
            if profile and profile.safety_features:
                self.safety_features_notes = profile.safety_features

    def save(self, *args, **kwargs):
        # Before saving, make sure we apply safety features if appropriate.
        self.apply_aircraft_safety_profile()
         # Auto-fill 107.39 waiver number from attached document if available
        if (
            self.operates_under_10739
            and self.oop_waiver_document
            and not self.oop_waiver_number
        ):
            number = getattr(self.oop_waiver_document, "waiver_number", None)
            if number:
                self.oop_waiver_number = number

        super().save(*args, **kwargs)


    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Waiver Planning Entry"
        verbose_name_plural = "Waiver Planning Entries"

    def __str__(self) -> str:
        if self.waiver:
            return f"Planning for {self.waiver.operation_title}"
        return f"Planning draft by {self.user}"
