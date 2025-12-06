from django import forms
from .models import AirspaceWaiver, WaiverPlanning
from equipment.models import Equipment
from pilot.models import PilotProfile



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

TZ_CHOICES = [
    ("America/New_York", "America/New_York"),
    ("America/Chicago", "America/Chicago"),
    ("America/Denver", "America/Denver"),
    ("America/Los_Angeles", "America/Los_Angeles"),
]

RADIUS_CHOICES = [
    ("0.1", "0.1 NM"),
    ("0.25", "0.25 NM"),
    ("0.5", "0.5 NM"),
    ("1.0", "1 NM"),
]

AIRSPACE_CLASS_CHOICES = [
    ("B", "Class B"),
    ("C", "Class C"),
    ("D", "Class D"),
    ("E", "Class E"),
    ("G", "Class G"),
]

YES_NO_CHOICES = [
    (False, "No"),
    (True, "Yes"),
]

DIRECTION_NS_CHOICES = [
    ("N", "N"),
    ("S", "S"),
]

DIRECTION_EW_CHOICES = [
    ("E", "E"),
    ("W", "W"),
]


class AirspaceWaiverForm(forms.ModelForm):
    # 1. Operation overview
    operation_title = forms.CharField(
        label="Operation Title",
        max_length=200,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "NHRA National Event FPV Operations"}
        ),
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        required=True,
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        required=True,
    )
    timeframe = forms.ChoiceField(
        choices=TIMEFRAME_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    local_timezone = forms.ChoiceField(
        label="Local Time Zone",
        choices=TZ_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # 2. Location
    proposed_location = forms.CharField(
        label="Proposed Location of Operation",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Venue name, city/state, brief description...",
            }
        ),
    )
    max_agl = forms.IntegerField(
        label="Proposed Maximum Flight Altitude (AGL, ft)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    )

    # Latitude (DMS)
    lat_degrees = forms.IntegerField(
        label="Latitude Degrees",
        min_value=0,
        max_value=90,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Enter Degrees"}
        ),
    )
    lat_minutes = forms.IntegerField(
        label="Latitude Minutes",
        min_value=0,
        max_value=59,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Enter Minutes"}
        ),
    )
    lat_seconds = forms.DecimalField(
        label="Latitude Seconds",
        min_value=0,
        max_value=59.9999,
        decimal_places=4,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Enter Seconds"}
        ),
    )
    lat_direction = forms.ChoiceField(
        label="Latitude Direction",
        choices=DIRECTION_NS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # Longitude (DMS)
    lon_degrees = forms.IntegerField(
        label="Longitude Degrees",
        min_value=0,
        max_value=180,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Enter Degrees"}
        ),
    )
    lon_minutes = forms.IntegerField(
        label="Longitude Minutes",
        min_value=0,
        max_value=59,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Enter Minutes"}
        ),
    )
    lon_seconds = forms.DecimalField(
        label="Longitude Seconds",
        min_value=0,
        max_value=59.9999,
        decimal_places=4,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Enter Seconds"}
        ),
    )
    lon_direction = forms.ChoiceField(
        label="Longitude Direction",
        choices=DIRECTION_EW_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    radius_nm = forms.ChoiceField(
        label="Radius (NM)",
        choices=RADIUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    nearest_airport = forms.CharField(
        label="Nearest Airport (ICAO)",
        max_length=10,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "KIND"}),
    )
    airspace_class = forms.ChoiceField(
        label="Class of Airspace",
        choices=AIRSPACE_CLASS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # 3. Description & waivers
    short_description = forms.CharField(
        label="Description of Your Proposed Operation",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Purpose of operation and how it will be safely conducted...",
            }
        ),
    )
    has_related_waiver = forms.TypedChoiceField(
        label="Is there a pending or approved waiver associated with this operation?",
        choices=YES_NO_CHOICES,
        coerce=lambda v: v == "True",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    related_waiver_details = forms.CharField(
        label="Relevant Existing Waivers (details)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "If yes, list waiver number(s), regulation(s) waived, expiry date(s)...",
            }
        ),
    )

    class Meta:
        model = AirspaceWaiver
        # We let Django include all model fields except these internal ones.
        exclude = (
            "user",
            "lat_decimal",
            "lon_decimal",
            "status",
            "created_at",
            "updated_at",
            "conops_text",
            "conops_generated_at",
        )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Optional: restrict aircraft dropdown to this user's drones
        if "aircraft" in self.fields and user is not None:
            self.fields["aircraft"].queryset = Equipment.objects.filter(
                owner=user,
                type="Drone",
            )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned






class WaiverPlanningForm(forms.ModelForm):
    """
    Step 1 – planning form that collects non-FAA waiver info
    used to enrich the CONOPS: aircraft, pilot, hours, launch location,
    and safety features.
    """

    aircraft = forms.ModelChoiceField(
        label="Drone Model",
        required=False,
        queryset=Equipment.objects.none(),  # set in __init__
        empty_label="Select drone (or enter manually below)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    pilot_profile = forms.ModelChoiceField(
        label="Pilot (from Pilot Profile)",
        required=False,
        queryset=PilotProfile.objects.none(),  # set in __init__
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    pilot_flight_hours = forms.DecimalField(
        label="Approximate UAS Flight Hours",
        required=False,
        min_value=0,
        max_digits=7,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g., 500.0",
            }
        ),
    )

    class Meta:
        model = WaiverPlanning
        fields = [
            "aircraft",
            "aircraft_manual",
            "pilot_profile",
            "pilot_name_manual",
            "pilot_cert_manual",
            "pilot_flight_hours",
            "launch_location",
            "safety_features_notes",
        ]
        widgets = {
            "aircraft_manual": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Other aircraft / additional drones (optional)",
                }
            ),
            "pilot_name_manual": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Pilot name (if not using a profile)",
                }
            ),
            "pilot_cert_manual": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Part 107 certificate # (if not using a profile)",
                }
            ),
            "launch_location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., paddock roof, media platform, staging area",
                }
            ),
            "safety_features_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Redundancies, geofencing, RTH, parachute, etc.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        # Pull user out of kwargs safely
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # --- Querysets ---

        # Pilot dropdown: scope to this user if your model uses user FK
        if user is not None:
            self.fields["pilot_profile"].queryset = PilotProfile.objects.filter(
                user=user
            ).order_by("user__first_name", "user__last_name")
        else:
            self.fields["pilot_profile"].queryset = PilotProfile.objects.all().order_by(
                "user__first_name", "user__last_name"
            )

        # Drone dropdown: only active drones from Equipment
        self.fields["aircraft"].queryset = Equipment.objects.filter(
            equipment_type="Drone",
            active=True,
        ).order_by("brand", "model", "name")

        # --- Pretty labels for dropdowns ---

        # Pilot labels: "FirstName LastName" (fallback to username)
        def pilot_label(obj):
            u = obj.user
            full = f"{u.first_name} {u.last_name}".strip()
            return full or u.username

        self.fields["pilot_profile"].label_from_instance = pilot_label

        # Drone labels: "Brand Model — FAA X, SN Y"
        def aircraft_label(obj):
            parts = []
            if obj.name:
                parts.append(obj.name)
        
            main = " ".join(parts) if parts else obj.name

            return main

        self.fields["aircraft"].label_from_instance = aircraft_label

        # --- Prefill cert + flight hours from PilotProfile on EDIT only ---
        instance = getattr(self, "instance", None)
        if instance and instance.pk and instance.pilot_profile:
            profile = instance.pilot_profile

            # Cert: only if manual cert is blank and profile has license_number
            if (
                not instance.pilot_cert_manual
                and getattr(profile, "license_number", None)
            ):
                self.initial.setdefault("pilot_cert_manual", profile.license_number)

            # UAS flight hours from profile.flight_time_total() (seconds → hours)
            if not instance.pilot_flight_hours:
                total_seconds = profile.flight_time_total() or 0
                hours_value = round(total_seconds / 3600.0, 1)
                if hours_value > 0:
                    self.initial.setdefault("pilot_flight_hours", hours_value)
