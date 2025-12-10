# airspace/forms.py

from django import forms

from .models import WaiverPlanning
from equipment.models import Equipment
from pilot.models import PilotProfile
# from documents.models import GeneralDocument  # if/when you scope docs by user


TZ_CHOICES = [
    ("America/New_York", "America/New_York"),
    ("America/Chicago", "America/Chicago"),
    ("America/Denver", "America/Denver"),
    ("America/Los_Angeles", "America/Los_Angeles"),
]


# airspace/forms.py

from django import forms

from .models import WaiverPlanning
from equipment.models import Equipment
from pilot.models import PilotProfile
from .utils import dms_to_decimal   # we'll use this to convert DMS -> decimal

TZ_CHOICES = [
    ("America/New_York", "America/New_York"),
    ("America/Chicago", "America/Chicago"),
    ("America/Denver", "America/Denver"),
    ("America/Los_Angeles", "America/Los_Angeles"),
]

RADIUS_CHOICES = [
    ("0.1", "1/10th NM"),
    ("0.25", "1/4th NM"),
    ("0.5", "1/2 NM"),
    ("0.75", "3/4th NM"),
    ("1.0", "1 NM"),
    ("1-2", "1–2 NM"),
    ("2-3", "2–3 NM"),
    ("blanket", "Blanket Area / Wide Area"),
]

DIRECTION_NS_CHOICES = [("N", "N"), ("S", "S")]
DIRECTION_EW_CHOICES = [("E", "E"), ("W", "W")]


class WaiverPlanningForm(forms.ModelForm):
    # --- DMS fields for latitude/longitude (form-only fields) ---
    lat_deg = forms.IntegerField(label="Lat °", required=False, min_value=0, max_value=90)
    lat_min = forms.IntegerField(label="Lat ′", required=False, min_value=0, max_value=59)
    lat_sec = forms.DecimalField(label="Lat ″", required=False, min_value=0, max_value=59, decimal_places=3)
    lat_dir = forms.ChoiceField(label="Lat Dir", required=False, choices=DIRECTION_NS_CHOICES)

    lon_deg = forms.IntegerField(label="Lon °", required=False, min_value=0, max_value=180)
    lon_min = forms.IntegerField(label="Lon ′", required=False, min_value=0, max_value=59)
    lon_sec = forms.DecimalField(label="Lon ″", required=False, min_value=0, max_value=59, decimal_places=3)
    lon_dir = forms.ChoiceField(label="Lon Dir", required=False, choices=DIRECTION_EW_CHOICES)

    class Meta:
        model = WaiverPlanning
        fields = [
            # --- Operation basics ---
            "operation_title",
            "start_date",
            "end_date",
            "timeframe",
            "frequency",
            "local_time_zone",
            "proposed_agl",

            # --- Aircraft ---
            "aircraft",
            "aircraft_manual",

            # --- Pilot ---
            "pilot_profile",
            "pilot_name_manual",
            "pilot_cert_manual",
            "pilot_flight_hours",

            # --- Venue & Location ---
            "venue_name",
            "street_address",
            "location_city",
            "location_state",
            "zip_code",
            "location_radius",      # now a dropdown
            "nearest_airport",
            # note: location_latitude/longitude still in the model but will be
            # set from DMS fields in clean(), so we don't expose them directly

            # --- Launch location description ---
            "launch_location",

            # --- 107.39 OOP ---
            "operates_under_10739",
            "oop_waiver_document",
            "oop_waiver_number",

            # --- Safety equipment / VO / insurance ---
            "uses_drone_detection",
            "uses_flight_tracking",
            "has_visual_observer",
            # "visual_observer_names",  # ⬅ removed from form as requested
            "insurance_provider",
            "insurance_coverage_limit",

            # --- Safety features / mitigations ---
            "safety_features_notes",
        ]

        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "proposed_agl": forms.NumberInput(attrs={"min": "0"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Friendly placeholder
        self.fields["operation_title"].widget.attrs.setdefault(
            "placeholder", "e.g., NHRA Nationals FPV Coverage"
        )

        # Time zone as select
        self.fields["local_time_zone"].widget = forms.Select(choices=TZ_CHOICES)
        if not self.initial.get("local_time_zone") and not self.instance.local_time_zone:
            self.fields["local_time_zone"].initial = "America/Indiana/Indianapolis"

        # Radius as dropdown
        self.fields["location_radius"].widget = forms.Select(
            choices=[("", "Select Radius")] + RADIUS_CHOICES
        )

        # Pilot profile queryset + label (First Last)
        if user is not None and "pilot_profile" in self.fields:
            qs = (
                PilotProfile.objects.filter(user=user)
                .select_related("user")
                .order_by("user__first_name", "user__last_name")
            )
            self.fields["pilot_profile"].queryset = qs

            def label_from_instance(obj):
                full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
                return full_name or obj.user.username

            self.fields["pilot_profile"].label_from_instance = label_from_instance

        # Aircraft queryset
        if "aircraft" in self.fields:
            self.fields["aircraft"].queryset = (
                Equipment.objects.filter(active=True, equipment_type="Drone")
                .order_by("brand", "model")
            )

    def clean(self):
        cleaned = super().clean()

        # Handle DMS → decimal conversion
        lat_parts = [
            cleaned.get("lat_deg"),
            cleaned.get("lat_min"),
            cleaned.get("lat_sec"),
            cleaned.get("lat_dir"),
        ]
        lon_parts = [
            cleaned.get("lon_deg"),
            cleaned.get("lon_min"),
            cleaned.get("lon_sec"),
            cleaned.get("lon_dir"),
        ]

        # Only convert if *all* parts are provided for that coordinate
        if all(lat_parts):
            cleaned["location_latitude"] = dms_to_decimal(
                cleaned["lat_deg"],
                cleaned["lat_min"],
                cleaned["lat_sec"],
                cleaned["lat_dir"],
            )

        if all(lon_parts):
            cleaned["location_longitude"] = dms_to_decimal(
                cleaned["lon_deg"],
                cleaned["lon_min"],
                cleaned["lon_sec"],
                cleaned["lon_dir"],
            )

        return cleaned
