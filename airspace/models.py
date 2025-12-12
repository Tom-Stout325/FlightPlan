# airspace/models.py

from django.conf import settings
from django.db import models
from django.contrib.postgres.fields import ArrayField

from documents.models import GeneralDocument  # assumes you have this app/model


class WaiverPlanning(models.Model):
    """
    Holds planning details that are not part of the FAA waiver form itself but
    are critical for the waiver application and Description of Operations /
    CONOPS: aircraft, pilot, dates, location, safety features, and operational
    profile.
    """

    # -------------------------
    # Choices
    # -------------------------
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

    PURPOSE_OPERATIONS_CHOICES = [
        ("event_filming", "Event filming / broadcast"),
        ("pro_photography", "Professional aerial photography"),
        ("mapping_survey", "Mapping / survey"),
        ("infrastructure_inspection", "Infrastructure inspection"),
        ("public_safety", "Public safety / incident support"),
        ("training_proficiency", "Training / proficiency flights"),
        ("real_estate", "Real estate photography"),
    ]

    # --- Operational Profile & Environment ---

    OP_AIRCRAFT_COUNT_CHOICES = [
        ("single", "Single aircraft"),
        ("multi_sequential", "Multiple aircraft (sequential use)"),
        ("multi_simultaneous", "Multiple aircraft (simultaneous use)"),
    ]

    GROUND_ENVIRONMENT_CHOICES = [
        ("residential", "Residential property / housing"),
        ("commercial", "Commercial buildings / business areas"),
        ("industrial", "Industrial or construction sites"),
        ("agricultural", "Agricultural land / open fields"),
        ("forested", "Forested or rural terrain"),
        ("water", "Water features (lakes, rivers, coastlines)"),
        ("roadways", "Roadways / parking areas"),
        ("pedestrian", "Pedestrian walkways / public access areas"),
        ("recreational", "Recreational areas (parks, trails, fields)"),
        ("infrastructure", "Critical infrastructure (utilities, towers, pipelines)"),
        ("unpopulated", "Unpopulated or remote terrain"),
        ("crowd_sparse", "Sparse people present"),
        ("crowd_moderate", "Moderate public presence"),
        ("crowd_dense", "Dense gatherings / event crowds"),
    ]


    PREPARED_PROCEDURES_CHOICES = [
        ("preflight", "Pre-flight checklist used"),
        ("postflight", "Post-flight checklist used"),
        ("lost_link", "Lost-link / flyaway procedure in place"),
        ("emergency_lz", "Emergency landing zones pre-identified"),
    ]

    # -------------------------
    # Ownership
    # -------------------------
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="waiver_planning_entries",
    )

    # -------------------------
    # Operation basics
    # -------------------------
    operation_title = models.CharField(
        max_length=255,
        help_text="Short title for this operation (e.g., 'NHRA Nationals FPV Coverage').",
    )
    start_date = models.DateField(
        help_text="First date on which operations will occur."
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last date on which operations will occur (optional if single day).",
    )
    timeframe = ArrayField(
        base_field=models.CharField(
            max_length=20,
            choices=TIMEFRAME_CHOICES,
        ),
        blank=True,
        default=list,
        help_text="Select all timeframes you expect to operate.",
    )
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        blank=True,
        help_text="How often operations will occur during this date range.",
    )
    local_time_zone = models.CharField(
        max_length=64,
        blank=True,
        help_text="Local time zone for the operation (e.g., America/New_York).",
    )
    proposed_agl = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum planned altitude AGL in feet.",
    )

    # -------------------------
    # Aircraft
    # -------------------------
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

    # -------------------------
    # Pilot
    # -------------------------
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

    # -------------------------
    # Waivers (107.39 & 107.145)
    # -------------------------
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

    operates_under_107145 = models.BooleanField(
        default=False,
        help_text=(
            "Check if this operation will be conducted under an approved "
            "14 CFR §107.145 Operations Over Moving Vehicles waiver."
        ),
    )
    mv_waiver_document = models.ForeignKey(
        GeneralDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mv_waiver_planning_entries",
        help_text="Select your approved 107.145 waiver from General Documents.",
    )
    mv_waiver_number = models.CharField(
        "Approved 107.145 Waiver Number",
        max_length=100,
        blank=True,
        help_text="Example: 107W-2024-04567",
    )

    # -------------------------
    # Purpose of Operations
    # -------------------------
    purpose_operations = ArrayField(
        base_field=models.CharField(
            max_length=50,
            choices=PURPOSE_OPERATIONS_CHOICES,
        ),
        blank=True,
        default=list,
        help_text="Select all purposes that apply to this operation.",
    )
    purpose_operations_details = models.TextField(
        blank=True,
        null=True,
        help_text="Additional context about how the drone will be used.",
    )

    # -------------------------
    # Venue & Location
    # -------------------------
    venue_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the venue (e.g., 'Lucas Oil Raceway').",
    )
    street_address = models.CharField(
        max_length=255,
        blank=True,
        help_text="Street address of the venue or operation area.",
    )
    location_city = models.CharField(
        max_length=100,
        blank=True,
        help_text="City where the operation will occur.",
    )
    location_state = models.CharField(
        max_length=100,
        blank=True,
        help_text="State where the operation will occur.",
    )
    zip_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="ZIP or postal code for the operation location.",
    )
    location_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude of the center point for operations.",
    )
    location_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude of the center point for operations.",
    )
    airspace_class = models.CharField(
        max_length=1,
        choices=AIRSPACE_CLASS_CHOICES,
        blank=True,
        help_text="Class of airspace where operations will occur.",
    )

    location_radius = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Radius from the center point (in NM or blanket area).",
    )
    nearest_airport = models.CharField(
        max_length=255,
        blank=True,
        help_text="Nearest airport (e.g., 'KIND – Indianapolis Intl').",
    )

    # -------------------------
    # Launch location & safety features
    # -------------------------
    launch_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Typical launch location or staging area for this waiver.",
    )

    uses_drone_detection = models.BooleanField(
        default=False,
        help_text="Drone detection system (e.g., AirSentinel) will be used.",
    )
    uses_flight_tracking = models.BooleanField(
        default=False,
        help_text="Flight tracking (e.g., FlightAware / ADS-B) will be monitored.",
    )
    has_visual_observer = models.BooleanField(
        default=False,
        help_text="One or more Visual Observers will be used.",
    )
    # visual_observer_names removed: we’ll capture VO details later in the app
    insurance_provider = models.CharField(
        max_length=255,
        blank=True,
        help_text="Insurance provider for this operation (optional).",
    )
    insurance_coverage_limit = models.CharField(
        max_length=100,
        blank=True,
        help_text="Coverage limit (e.g., '$5,000,000').",
    )

    safety_features_notes = models.TextField(
        blank=True,
        help_text=(
            "Key safety features, redundancies, or geofencing used for this operation. "
            "If a drone with a safety profile is selected, this will be auto-filled."
        ),
    )

    # -------------------------
    # Operational Profile
    # -------------------------
    aircraft_count = models.CharField(
        max_length=25,
        choices=OP_AIRCRAFT_COUNT_CHOICES,
        blank=True,
        help_text="Number of aircraft used for this operation.",
    )
    flight_duration = models.CharField(
        max_length=50,
        blank=True,
        help_text="Typical flight duration (e.g., 5–10 min).",
    )
    flights_per_day = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Approximate number of flights per day (used for narrative only).",
    )
    ground_environment = ArrayField(
        base_field=models.CharField(
            max_length=50,
            choices=GROUND_ENVIRONMENT_CHOICES,
        ),
        blank=True,
        default=list,
        help_text="Types of ground environment present in the area.",
    )

    # NEW: Free-text additions
    ground_environment_other = models.TextField(
        blank=True,
        help_text=(
            "Any additional ground environment types not covered by the "
            "checkbox list (e.g., rail yards, marinas, refineries, etc.)."
        ),
    )

    estimated_crowd_size = models.CharField(
        max_length=50,
        blank=True,
        help_text="Estimated maximum crowd size (e.g., 15,000). Leave blank if unknown.",
    )

    prepared_procedures = ArrayField(
        base_field=models.CharField(
            max_length=30,
            choices=PREPARED_PROCEDURES_CHOICES,
        ),
        blank=True,
        default=list,
        help_text="Safety procedures used during operations.",
    )

    # -------------------------
    # Timestamps
    # -------------------------
    generated_description_at = models.DateTimeField(null=True, blank=True)

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
        if self.pilot_profile and getattr(self.pilot_profile, "license_number", None):
            return self.pilot_profile.license_number
        return ""

    def aircraft_display(self) -> str:
        if self.aircraft:
            return str(self.aircraft)
        if self.aircraft_manual:
            return self.aircraft_manual
        return ""

    def timeframe_codes(self):
        """
        Returns timeframe as a list of codes.
        Supports both ArrayField (native list) and legacy CSV storage.
        """
        if not self.timeframe:
            return []
        if isinstance(self.timeframe, (list, tuple)):
            return list(self.timeframe)
        return [c.strip() for c in str(self.timeframe).split(",") if c.strip()]

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
        # Apply safety features from aircraft profile if appropriate
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

        # Auto-fill 107.145 waiver number from attached document if available
        if (
            self.operates_under_107145
            and self.mv_waiver_document
            and not self.mv_waiver_number
        ):
            number = getattr(self.mv_waiver_document, "waiver_number", None)
            if number:
                self.mv_waiver_number = number

        # If you have an update_decimal_coords helper elsewhere, call it safely
        if hasattr(self, "update_decimal_coords"):
            self.update_decimal_coords()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.operation_title} ({self.user})"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Waiver Planning Entry"
        verbose_name_plural = "Waiver Planning Entries"







class WaiverApplication(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="waiver_applications",
    )
    planning = models.ForeignKey(
        WaiverPlanning,
        on_delete=models.CASCADE,
        related_name="applications",
    )

    # This will hold the generated Description of Operations text
    description = models.TextField(
        blank=True,
        help_text="Generated Description of Operations for this waiver.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )
    locked_description = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Waiver Application for {self.planning.operation_title} ({self.user})"




#------------------------------------
#               C O N O P S
#------------------------------------



class ConopsSection(models.Model):
    """
    One section of a CONOPS document for an FAA waiver application.
    Sections may be AI-generated or manually edited and locked.
    """

    application = models.ForeignKey(
        "airspace.WaiverApplication",
        on_delete=models.CASCADE,
        related_name="conops_sections",
    )

    # Stable internal key (used by code & AI prompts)
    section_key = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Internal identifier, e.g. 'purpose_of_operations'",
    )

    # Human-readable heading
    title = models.CharField(
        max_length=150,
        help_text="Section title shown in the CONOPS document",
    )

    # Section body (AI-generated or edited)
    content = models.TextField(blank=True)

    # Prevent accidental regeneration
    locked = models.BooleanField(default=False)


    section_key = models.SlugField()
    title = models.CharField(max_length=255)

    content = models.TextField(blank=True)
    locked = models.BooleanField(default=False)

    is_complete = models.BooleanField(default=False)
    validated_at = models.DateTimeField(null=True, blank=True)

    generated_at = models.DateTimeField(null=True, blank=True)
    # Metadata
    generated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("application", "section_key")
        ordering = ["id"]

    def __str__(self):
        return f"{self.application_id} – {self.title}"
