# airspace/forms.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms
from dal import autocomplete

from equipment.models import Equipment
from pilot.models import PilotProfile

from .models import Airport, WaiverApplication, WaiverPlanning

# NOTE: We intentionally do NOT import dms_to_decimal from utils here
# because the file previously redefined it, which is confusing.
# If you have a canonical util, we can switch to that later.


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


def _dms_to_decimal(deg, minutes, seconds, direction) -> Decimal:
    """
    Convert DMS parts to signed decimal degrees.
    Returns Decimal quantized to 6 dp (to match model DecimalField).
    """
    deg = Decimal(deg)
    minutes = Decimal(minutes)
    seconds = Decimal(seconds)

    value = deg + (minutes / Decimal(60)) + (seconds / Decimal(3600))
    if direction in ("S", "W"):
        value = -value
    return value.quantize(Decimal("0.000001"))


def _qs_user_scoped(qs, user):
    """
    If the underlying model has a user_id field, scope by it.
    Otherwise return qs unchanged (for global tables like Airport).
    """
    if user is None:
        return qs
    model = qs.model
    if hasattr(model, "user_id") or any(f.name == "user" for f in model._meta.fields):
        return qs.filter(user=user)
    return qs


class WaiverPlanningForm(forms.ModelForm):
    """
    Main planning form for the Airspace waiver workflow.
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
    lat_deg = forms.IntegerField(required=False, min_value=0, max_value=90)
    lat_min = forms.IntegerField(required=False, min_value=0, max_value=59)
    lat_sec = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=Decimal("59.999"),
        decimal_places=3,
    )
    lat_dir = forms.ChoiceField(required=False, choices=DIRECTION_NS_CHOICES)

    lon_deg = forms.IntegerField(required=False, min_value=0, max_value=180)
    lon_min = forms.IntegerField(required=False, min_value=0, max_value=59)
    lon_sec = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=Decimal("59.999"),
        decimal_places=3,
    )
    lon_dir = forms.ChoiceField(required=False, choices=DIRECTION_EW_CHOICES)

    local_time_zone = forms.ChoiceField(
        choices=TZ_CHOICES,
        required=False,
        label="Local time zone",
        widget=forms.Select(attrs={"class": "form-select"}),
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
            "launch_location",

            # --- 107.39 OOP ---
            "operates_under_10739",
            "oop_waiver_document",
            "oop_waiver_number",

            # --- 107.145 Moving Vehicles ---
            "operates_under_107145",
            "mv_waiver_document",
            "mv_waiver_number",

            # --- Safety / VO / insurance ---
            "uses_drone_detection",
            "uses_flight_tracking",
            "has_visual_observer",
            "insurance_provider",
            "insurance_coverage_limit",
            "safety_features_notes",

            # --- Purpose / profile ---
            "purpose_operations",
            "purpose_operations_details",
            "aircraft_count",
            "flight_duration",
            "flights_per_day",
            "estimated_crowd_size",
            "ground_environment",
            "ground_environment_other",
            "prepared_procedures",

            # hidden / stored decimals (we control saving behavior)
            "location_latitude",
            "location_longitude",
        ]

        widgets = {
            "operation_title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., NHRA Nationals FPV Coverage"}
            ),
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "frequency": forms.Select(attrs={"class": "form-select"}),
            "proposed_agl": forms.NumberInput(attrs={"min": "0", "class": "form-control"}),

            "aircraft": forms.Select(attrs={"class": "form-select"}),
            "aircraft_manual": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., Avata 2, Mini 4 Pro"}
            ),

            "pilot_profile": forms.Select(attrs={"class": "form-select"}),
            "pilot_name_manual": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "If not in Pilot Profiles"}
            ),
            "pilot_cert_manual": forms.TextInput(attrs={"class": "form-control"}),
            "pilot_flight_hours": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),

            "venue_name": forms.TextInput(attrs={"class": "form-control"}),
            "street_address": forms.TextInput(attrs={"class": "form-control"}),
            "location_city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "location_state": forms.TextInput(attrs={"class": "form-control", "placeholder": "State (e.g. IN)"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control"}),

            "airspace_class": forms.Select(attrs={"class": "form-select"}),
            "location_radius": forms.Select(attrs={"class": "form-select"}),

            "nearest_airport_ref": autocomplete.ModelSelect2(
                url="airspace:airport-autocomplete",
                attrs={
                    "data-placeholder": "Type ICAO or airport name (e.g., KIND)",
                    "data-minimum-input-length": 1,
                },
            ),
            "nearest_airport": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Manual fallback (e.g., KIND – Indianapolis Intl)"}
            ),

            "purpose_operations_details": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "flight_duration": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 5–10 minutes"}
            ),
            "estimated_crowd_size": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. ~15,000 (if known)"}
            ),
            "flights_per_day": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "ground_environment_other": forms.Textarea(attrs={"class": "form-control", "rows": 2}),

            # Keep decimals hidden (we control these)
            "location_latitude": forms.HiddenInput(),
            "location_longitude": forms.HiddenInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        # Bootstrap classes (avoid stomping DAL widgets)
        for name, field in self.fields.items():
            w = field.widget
            if w.__class__.__module__.startswith("dal"):
                continue
            if isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            elif isinstance(w, (forms.TextInput, forms.Textarea, forms.NumberInput, forms.DateInput)):
                w.attrs.setdefault("class", "form-control")

        # Local time zone default
        if not (self.initial.get("local_time_zone") or getattr(self.instance, "local_time_zone", None)):
            self.initial["local_time_zone"] = TZ_CHOICES[0][0] if TZ_CHOICES else None

        # Radius dropdown choices
        if "location_radius" in self.fields:
            self.fields["location_radius"].widget = forms.Select(
                choices=[("", "Select Radius")] + RADIUS_CHOICES,
                attrs={"class": "form-select"},
            )

        # DMS helpers styling
        for name in ["lat_deg", "lat_min", "lat_sec", "lon_deg", "lon_min", "lon_sec"]:
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "form-control form-control-sm")
        for name in ["lat_dir", "lon_dir"]:
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "form-select form-select-sm")

        # Pilot profiles scoped to user
        if "pilot_profile" in self.fields:
            qs = PilotProfile.objects.select_related("user").all()
            qs = _qs_user_scoped(qs, self.user).order_by("user__first_name", "user__last_name", "user__username")
            self.fields["pilot_profile"].queryset = qs

            def label_from_instance(obj):
                full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
                return full_name or obj.user.username

            self.fields["pilot_profile"].label_from_instance = label_from_instance

        # Aircraft: scope to user if Equipment is owned, always active drones
        if "aircraft" in self.fields:
            qs = Equipment.objects.filter(active=True, equipment_type="Drone")
            qs = _qs_user_scoped(qs, self.user).order_by("brand", "model")
            self.fields["aircraft"].queryset = qs

        # Waiver documents: if GeneralDocument is user-owned, scope it
        for doc_field in ("oop_waiver_document", "mv_waiver_document"):
            if doc_field in self.fields:
                qs = self.fields[doc_field].queryset
                # queryset exists because FK field is on the model
                self.fields[doc_field].queryset = _qs_user_scoped(qs, self.user)

        # Airport FK sanity queryset (global table)
        if "nearest_airport_ref" in self.fields:
            self.fields["nearest_airport_ref"].queryset = Airport.objects.filter(active=True).order_by("icao")

    def _selected_pilot(self):
        """
        Only return a pilot profile owned by the current user (when user is provided).
        """
        if self.is_bound:
            raw = (self.data.get("pilot_profile") or "").strip()
            if raw.isdigit():
                qs = PilotProfile.objects.select_related("user").filter(pk=int(raw))
                qs = _qs_user_scoped(qs, self.user)
                return qs.first()
            return None

        pilot = getattr(self.instance, "pilot_profile", None)
        if pilot and self.user is not None and hasattr(pilot, "user_id") and pilot.user_id != self.user.id:
            return None
        return pilot

    def _selected_aircraft(self):
        """
        Only return an aircraft owned by the current user (when user is provided).
        """
        if self.is_bound:
            raw = (self.data.get("aircraft") or "").strip()
            if raw.isdigit():
                qs = Equipment.objects.filter(pk=int(raw), equipment_type="Drone")
                qs = _qs_user_scoped(qs, self.user)
                return qs.first()
            return None

        ac = getattr(self.instance, "aircraft", None)
        if ac and self.user is not None and hasattr(ac, "user_id") and ac.user_id != self.user.id:
            return None
        return ac

    def clean(self):
        cleaned = super().clean()

        # -------------------------
        # Reject cross-user FK posts early (nice form errors)
        # -------------------------
        if self.user is not None:
            pilot = cleaned.get("pilot_profile")
            if pilot is not None and hasattr(pilot, "user_id") and pilot.user_id != self.user.id:
                self.add_error("pilot_profile", "Invalid selection.")

            aircraft = cleaned.get("aircraft")
            if aircraft is not None and hasattr(aircraft, "user_id") and aircraft.user_id != self.user.id:
                self.add_error("aircraft", "Invalid selection.")

            for doc_field in ("oop_waiver_document", "mv_waiver_document"):
                doc = cleaned.get(doc_field)
                if doc is not None and hasattr(doc, "user_id") and doc.user_id != self.user.id:
                    self.add_error(doc_field, "Invalid selection.")

        # -------------------------
        # Pilot auto-fill (server-side)
        # -------------------------
        pilot = self._selected_pilot()
        if pilot:
            if not cleaned.get("pilot_cert_manual") and (pilot.license_number or "").strip():
                cleaned["pilot_cert_manual"] = pilot.license_number

            if not cleaned.get("pilot_flight_hours"):
                total_seconds = pilot.flight_time_total()
                if total_seconds:
                    cleaned["pilot_flight_hours"] = round(total_seconds / 3600, 1)

        # -------------------------
        # DMS -> Decimal coords
        # -------------------------
        lat_parts = [cleaned.get("lat_deg"), cleaned.get("lat_min"), cleaned.get("lat_sec"), cleaned.get("lat_dir")]
        lon_parts = [cleaned.get("lon_deg"), cleaned.get("lon_min"), cleaned.get("lon_sec"), cleaned.get("lon_dir")]

        lat_complete = all(part not in (None, "") for part in lat_parts)
        lon_complete = all(part not in (None, "") for part in lon_parts)

        if lat_complete:
            try:
                cleaned["location_latitude"] = _dms_to_decimal(
                    cleaned["lat_deg"], cleaned["lat_min"], cleaned["lat_sec"], cleaned["lat_dir"]
                )
            except (InvalidOperation, ValueError):
                self.add_error("lat_sec", "Invalid latitude value.")

        if lon_complete:
            try:
                cleaned["location_longitude"] = _dms_to_decimal(
                    cleaned["lon_deg"], cleaned["lon_min"], cleaned["lon_sec"], cleaned["lon_dir"]
                )
            except (InvalidOperation, ValueError):
                self.add_error("lon_sec", "Invalid longitude value.")

        # HARDEN: If DMS not provided, do NOT accept posted hidden coords
        # (prevents client-side tampering / stale hidden input injection)
        if not lat_complete:
            cleaned["location_latitude"] = getattr(self.instance, "location_latitude", None)
        if not lon_complete:
            cleaned["location_longitude"] = getattr(self.instance, "location_longitude", None)

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        # FK fields explicitly (prevents silent drops)
        instance.aircraft = self.cleaned_data.get("aircraft")
        instance.pilot_profile = self.cleaned_data.get("pilot_profile")
        instance.nearest_airport_ref = self.cleaned_data.get("nearest_airport_ref")

        # DMS -> model decimals (we control these)
        instance.location_latitude = self.cleaned_data.get("location_latitude")
        instance.location_longitude = self.cleaned_data.get("location_longitude")

        # Safety features fallback (server-side)
        if instance.aircraft and not (instance.safety_features_notes or "").strip():
            profile = getattr(instance.aircraft, "drone_safety_profile", None)
            if profile and (profile.safety_features or "").strip():
                instance.safety_features_notes = profile.safety_features

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
