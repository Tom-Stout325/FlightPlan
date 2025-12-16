# airspace/forms.py

from django import forms
from dal import autocomplete

from equipment.models import Equipment
from pilot.models import PilotProfile
from .utils import dms_to_decimal  # used to convert DMS -> decimal

from .models import WaiverPlanning, WaiverApplication






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

# -------------------------------------------------------------------
# Form-local choices for checkbox groups
# (kept separate from the model so they always have values)
# -------------------------------------------------------------------
TIMEFRAME_CHOICES = [
    ("sunrise_noon", "Sunrise to Noon"),
    ("noon_4pm", "Noon to 4 PM"),
    ("4pm_sunset", "4 PM to Sunset"),
    ("night", "Night"),
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


class WaiverPlanningForm(forms.ModelForm):
    """
    Main planning form for the Airspace waiver workflow.
    Collects operation, aircraft, pilot, location, safety, and
    operational profile data that will feed the Waiver Application
    and Description of Operations / CONOPS generator.
    """
    
    timeframe = forms.MultipleChoiceField(
        choices=TIMEFRAME_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Requested Timeframes",
    )

    purpose_operations = forms.MultipleChoiceField(
        choices=PURPOSE_OPERATIONS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Purpose of Drone Operations",
    )

    ground_environment = forms.MultipleChoiceField(
        choices=GROUND_ENVIRONMENT_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Ground Environment",
    )

    prepared_procedures = forms.MultipleChoiceField(
        choices=PREPARED_PROCEDURES_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Operational Procedures",
    )


    # --- DMS fields for latitude/longitude (form-only fields) ---
    lat_deg = forms.IntegerField(
        label="Lat °",
        required=False,
        min_value=0,
        max_value=90,
    )
    lat_min = forms.IntegerField(
        label="Lat ′",
        required=False,
        min_value=0,
        max_value=59,
    )
    lat_sec = forms.DecimalField(
        label="Lat ″",
        required=False,
        min_value=0,
        max_value=59,
        decimal_places=3,
    )
    lat_dir = forms.ChoiceField(
        label="Lat Dir",
        required=False,
        choices=DIRECTION_NS_CHOICES,
    )

    lon_deg = forms.IntegerField(
        label="Lon °",
        required=False,
        min_value=0,
        max_value=180,
    )
    lon_min = forms.IntegerField(
        label="Lon ′",
        required=False,
        min_value=0,
        max_value=59,
    )
    lon_sec = forms.DecimalField(
        label="Lon ″",
        required=False,
        min_value=0,
        max_value=59,
        decimal_places=3,
    )
    lon_dir = forms.ChoiceField(
        label="Lon Dir",
        required=False,
        choices=DIRECTION_EW_CHOICES,
    )

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
            "airspace_class", 
            "location_radius",
            "nearest_airport_ref",
            "nearest_airport",

            # --- Launch location description ---
            "launch_location",

            # --- 107.39 OOP ---
            "operates_under_10739",
            "oop_waiver_document",
            "oop_waiver_number",

            # --- 107.145 Over Moving Vehicles ---
            "operates_under_107145",    
            "mv_waiver_document",
            "mv_waiver_number",

            # --- Safety equipment / VO / insurance ---
            "uses_drone_detection",
            "uses_flight_tracking",
            "has_visual_observer",
            "insurance_provider",
            "insurance_coverage_limit",

            # --- Safety features / mitigations ---
            "safety_features_notes",

            # --- Purpose of Operations (ArrayField, mapped via field above) ---
            "purpose_operations",
            "purpose_operations_details",

            # --- Operational Profile & Environment ---
            "aircraft_count",
            "flight_duration",
            "flights_per_day",
            "estimated_crowd_size",
            "ground_environment",
            "ground_environment_other",
            "prepared_procedures",
        ]


        widgets = {
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "proposed_agl": forms.NumberInput(
                attrs={"min": "0", "class": "form-control"}
            ),
            "location_city": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "City"}
            ),
            "location_state": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "State (e.g. IN)"}
            ),
            "nearest_airport_ref": autocomplete.ModelSelect2(
                url="airspace:airport-autocomplete",
                attrs={
                    "data-placeholder": "Type ICAO or airport name (e.g., KIND)",
                    "class": "form-select",
                },
            ),
            "nearest_airport": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Manual fallback (e.g., KIND – Indianapolis Intl)",
                }
            ),            
            "airspace_class": forms.Select(attrs={"class": "form-select"}),
            "purpose_operations_details": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "e.g. Live broadcast coverage of NHRA national events for television…",
                }
            ),
            "flight_duration": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 5–10 minutes"}
            ),
            "estimated_crowd_size": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. ~15,000 (if known)"}
            ),
            "flights_per_day": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "placeholder": "Approximate (used for narrative only)",
                }
            ),
            "ground_environment_other": forms.Textarea( 
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "e.g. Rail yard on north boundary; marina along riverfront…",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Friendly placeholder for operation title
        if "operation_title" in self.fields:
            self.fields["operation_title"].widget.attrs.setdefault(
                "placeholder", "e.g., NHRA Nationals FPV Coverage"
            )
            self.fields["operation_title"].widget.attrs.setdefault(
                "class", "form-control"
            )

        # Add Bootstrap styling to standard widgets
        for name, field in self.fields.items():
            if isinstance(
                field.widget,
                (forms.TextInput, forms.Textarea, forms.Select, forms.NumberInput),
            ):
                field.widget.attrs.setdefault("class", "form-control")

        # Local time zone as select with default
        if "local_time_zone" in self.fields:
            self.fields["local_time_zone"].widget = forms.Select(
                choices=TZ_CHOICES,
                attrs={"class": "form-select"},
            )
            if (
                not self.initial.get("local_time_zone")
                and not getattr(self.instance, "local_time_zone", None)
            ):
                self.fields["local_time_zone"].initial = "America/Indiana/Indianapolis"

        # Radius dropdown
        if "location_radius" in self.fields:
            self.fields["location_radius"].widget = forms.Select(
                choices=[("", "Select Radius")] + RADIUS_CHOICES,
                attrs={"class": "form-select"},
            )

        # DMS helper fields – small controls
        for name in ["lat_deg", "lat_min", "lat_sec", "lon_deg", "lon_min", "lon_sec"]:
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault(
                    "class", "form-control form-control-sm"
                )
        for name in ["lat_dir", "lon_dir"]:
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault(
                    "class", "form-select form-select-sm"
                )

        # Pilot profile queryset + label
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

        # Aircraft queryset: only active drones
        if "aircraft" in self.fields:
            self.fields["aircraft"].queryset = (
                Equipment.objects.filter(active=True, equipment_type="Drone")
                .order_by("brand", "model")
            )
            self.fields["aircraft"].widget.attrs.setdefault("class", "form-select")
        
        nearest_airport_field = self.fields.get("nearest_airport")
        if nearest_airport_field:
            nearest_airport_field.widget.attrs.update({
            "class": "form-control",
            "placeholder": "Type ICAO (e.g., KIND)",
            "autocomplete": "off",
        })
        



    def clean(self):
        cleaned = super().clean()

        # --- DMS → decimal conversion ---
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

    def save(self, commit=True):
        """
        Ensure converted decimal latitude/longitude are saved on the model,
        even though those fields are not directly exposed in the form.
        """
        instance = super().save(commit=False)

        lat = self.cleaned_data.get("location_latitude")
        lon = self.cleaned_data.get("location_longitude")

        if lat is not None:
            instance.location_latitude = lat
        if lon is not None:
            instance.location_longitude = lon

        if commit:
            instance.save()
            self.save_m2m()

        return instance











class WaiverApplicationDescriptionForm(forms.ModelForm):
    """
    Step 2: Big text box that holds the Description of Operations.
    """
    class Meta:
        model = WaiverApplication
        fields = ["description"]
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 18,
                    "placeholder": "Description of Operations will appear here…",
                }
            )
        }
