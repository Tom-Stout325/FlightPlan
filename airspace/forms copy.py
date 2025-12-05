# airspace/forms.py

from django import forms
from .models import AirspaceWaiver


class AirspaceWaiverForm(forms.ModelForm):
    """
    Basic ModelForm for creating an AirspaceWaiver.
    We can fancy up widgets later – goal right now is to get
    the DB + CONOPS flow working end-to-end.
    """

    class Meta:
        model = AirspaceWaiver
        # List only the fields the user should fill out in the form
        fields = [
            "operation_title",
            "start_date",
            "end_date",
            "timeframe",
            "frequency",
            "local_timezone",
            "proposed_location",
            "max_agl",
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
            "short_description",
            "has_related_waiver",
            "related_waiver_details",
        ]

        # You can tweak these later for nicer UI; right now they can be defaults.
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "short_description": forms.Textarea(attrs={"rows": 3}),
            "proposed_location": forms.Textarea(attrs={"rows": 3}),
            "related_waiver_details": forms.Textarea(attrs={"rows": 3}),
        }
