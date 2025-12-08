from django import forms

from documents.models import GeneralDocument
from pilot.models import PilotProfile
from equipment.models import Equipment
from .models import AirspaceWaiver, WaiverPlanning



# ---------------------------------------------------------------------
# Choice constants
# ---------------------------------------------------------------------

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

DIRECTION_NS_CHOICES = [("N", "N"), ("S", "S")]
DIRECTION_EW_CHOICES = [("E", "E"), ("W", "W")]


class AirspaceWaiverBaseForm(forms.ModelForm):
    """
    Base form shared by all wizard steps.
    Handles:
      - common excludes
      - aircraft queryset
      - timeframe (multi-select) ↔ model CharField conversion
      - basic start/end date validation
    """

    class Meta:
        model = AirspaceWaiver
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Limit aircraft choices to active drones
        if "aircraft" in self.fields:
            self.fields["aircraft"].queryset = (
                Equipment.objects.filter(equipment_type="Drone", active=True)
                .order_by("brand", "model", "name")
            )

        # Prefill timeframe (model stores comma-separated string)
        if "timeframe" in self.fields and getattr(self.instance, "timeframe", None):
            current = self.instance.timeframe
            if isinstance(current, str):
                self.initial.setdefault(
                    "timeframe",
                    [v.strip() for v in current.split(",") if v.strip()],
                )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned

    def clean_timeframe(self):
        """
        Convert MultipleChoiceField (list) to comma-separated string
        for storage in the model CharField.
        """
        tf = self.cleaned_data.get("timeframe")
        if isinstance(tf, (list, tuple)):
            return ",".join(tf)
        return tf




class AirspaceWaiverOverviewForm(AirspaceWaiverBaseForm):
    """
    Step 1 – Operation Overview + Aircraft.
    Timeframe = multi-select checkboxes.
    Frequency = single-select dropdown.
    """

    timeframe = forms.MultipleChoiceField(
        label="Timeframe of Operation",
        required=True,
        choices=TIMEFRAME_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select all that apply.",
    )

    frequency = forms.ChoiceField(
        label="Frequency of Operation",
        required=True,
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    local_timezone = forms.ChoiceField(
        label="Local Time Zone",
        choices=TZ_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    operation_activities = forms.MultipleChoiceField(
        label="What are you doing?",
        required=False,
        choices=AirspaceWaiver.OPERATION_ACTIVITY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    operation_activities_other = forms.CharField(
        label="Additional details (optional)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "e.g. Live broadcast coverage of NHRA national events for television...",
            }
        ),
    )

    class Meta(AirspaceWaiverBaseForm.Meta):
        fields = [
            "operation_title",
            "start_date",
            "end_date",
            "timeframe",
            "frequency",
            "local_timezone",
            "aircraft",
            "aircraft_custom",
            "proposed_location",
            "max_agl",
            "operation_activities",
            "operation_activities_other",
        ]
        widgets = {
            "operation_title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "NHRA National Event FPV Operations",
                }
            ),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "aircraft_custom": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "If not in the list, describe the aircraft.",
                }
            ),
            "proposed_location": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Venue name, city/state, brief description...",
                }
            ),
            "max_agl": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
        }

    def clean_operation_activities(self):
        data = self.cleaned_data.get("operation_activities") or []
        if isinstance(data, (list, tuple)):
            return ",".join(data)
        return data





class AirspaceWaiverLocationForm(AirspaceWaiverBaseForm):
    """
    Step 2 – Location & Airspace details
    """

    radius_nm = forms.ChoiceField(
        label="Radius (NM)",
        required=True,
        choices=RADIUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(AirspaceWaiverBaseForm.Meta):
        fields = [
            "lat_degrees",
            "lat_minutes",
            "lat_seconds",
            "lat_direction",
            "lon_degrees",
            "lon_minutes",
            "lon_seconds",
            "lon_direction",
            "radius_nm",
            "nearest_airport",
            "airspace_class",
        ]
        widgets = {
            "lat_degrees": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Enter Degrees"}
            ),
            "lat_minutes": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Enter Minutes"}
            ),
            "lat_seconds": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Enter Seconds"}
            ),
            "lat_direction": forms.Select(attrs={"class": "form-select"}),
            "lon_degrees": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Enter Degrees"}
            ),
            "lon_minutes": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Enter Minutes"}
            ),
            "lon_seconds": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Enter Seconds"}
            ),
            "lon_direction": forms.Select(attrs={"class": "form-select"}),
            # You can remove this radius_nm widget if you want;
            # the field definition above already sets its widget.
            "nearest_airport": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "KIND"}
            ),
            "airspace_class": forms.Select(attrs={"class": "form-select"}),
        }





class AirspaceWaiverDescriptionForm(AirspaceWaiverBaseForm):
    """
    Step 3 – Operational Description & Existing Waivers
    """

    has_related_waiver = forms.TypedChoiceField(
        label="Is there a pending or approved waiver associated with this operation?",
        choices=YES_NO_CHOICES,
        coerce=lambda v: v == "True",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(AirspaceWaiverBaseForm.Meta):
        fields = [
            "short_description",
            "has_related_waiver",
            "related_waiver_details",
        ]
        widgets = {
            "short_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Purpose of operation and how it will be safely conducted...",
                }
            ),
            "related_waiver_details": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "If yes, list waiver number(s), regulation(s) waived, expiry date(s)...",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        has_related = cleaned.get("has_related_waiver")
        details = (cleaned.get("related_waiver_details") or "").strip()
        if has_related and str(has_related) == "True" and not details:
            self.add_error(
                "related_waiver_details",
                "Please provide details for the related waiver(s).",
            )
        return cleaned


# ---------------------------------------------------------------------
# WaiverPlanning form
# ---------------------------------------------------------------------


class WaiverPlanningForm(forms.ModelForm):
    """
    Planning form used to enrich the CONOPS:
    aircraft, pilot, hours, launch location, safety features, and
    whether the operation is under an existing 107.39 waiver.
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
            "operates_under_10739",
            "oop_waiver_document",
            "oop_waiver_number",
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
                    "placeholder": "Part 107 certificate number (if not using a profile)",
                }
            ),
            "launch_location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Launch/staging location (city, venue, or coordinates)",
                }
            ),
            "safety_features_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Redundancies, geofencing, RTH, parachute, etc.",
                }
            ),
            "operates_under_10739": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "oop_waiver_document": forms.Select(
                attrs={"class": "form-select"}
            ),
            "oop_waiver_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "107W-2024-01234",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Pilot dropdown
        if user is not None:
            self.fields["pilot_profile"].queryset = PilotProfile.objects.filter(
                user=user
            ).order_by("user__first_name", "user__last_name")
        else:
            self.fields["pilot_profile"].queryset = PilotProfile.objects.all().order_by(
                "user__first_name", "user__last_name"
            )

        # Drone dropdown
        self.fields["aircraft"].queryset = Equipment.objects.filter(
            equipment_type="Drone",
            active=True,
        ).order_by("brand", "model", "name")

        # Label formatting
        def pilot_label(obj):
            u = obj.user
            full = f"{u.first_name} {u.last_name}".strip()
            return full or u.username

        self.fields["pilot_profile"].label_from_instance = pilot_label

        def aircraft_label(obj):
            parts = [obj.brand, obj.model]
            base = " ".join(p for p in parts if p)
            if obj.name:
                return f"{base} ({obj.name})" if base else obj.name
            return base or str(obj)

        self.fields["aircraft"].label_from_instance = aircraft_label

        # Scope OOP waiver document dropdown
        if "oop_waiver_document" in self.fields:
            qs = GeneralDocument.objects.all()
            # If your GeneralDocument has a user FK, filter it here.
            try:
                # this will raise if field doesn't exist
                GeneralDocument._meta.get_field("user")
                if user is not None:
                    qs = qs.filter(user=user)
            except Exception:
                pass

            self.fields["oop_waiver_document"].queryset = qs.order_by("title")

        # Pre-fill waiver number from document, if present
        instance = getattr(self, "instance", None)
        if (
            instance
            and instance.pk
            and instance.oop_waiver_document
            and not instance.oop_waiver_number
        ):
            doc_number = getattr(instance.oop_waiver_document, "waiver_number", None)
            if doc_number:
                self.initial.setdefault("oop_waiver_number", doc_number)




class AirspaceWaiverForm(forms.ModelForm):
    """
    Full edit/create form for an AirspaceWaiver, used by:
      - airspace_waiver_form
      - airspace_waiver_edit
    This uses the model fields directly (single-page form), separate from the wizard.
    """

    class Meta:
        model = AirspaceWaiver
        fields = "__all__"