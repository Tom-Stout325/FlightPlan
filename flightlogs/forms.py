# flightlogs/forms.py
from __future__ import annotations

from django import forms

from .models import FlightLog


class FlightLogCSVUploadForm(forms.Form):
    """
    CSV upload form (for the import view only).
    """
    csv_file = forms.FileField(
        label="Upload Flight Log CSV",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".csv,text/csv",
            }
        ),
    )

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        name = (getattr(f, "name", "") or "").lower()
        if name and not name.endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file.")
        return f


class FlightLogForm(forms.ModelForm):
    """
    Safe edit/create form for FlightLog.
    Ownership is enforced in the view (user is excluded here).
    """

    class Meta:
        model = FlightLog
        exclude = ("user",)

        # Mobile-first widget defaults (Bootstrap-style)
        widgets = {
            "flight_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "landing_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),

            "flight_title": forms.TextInput(attrs={"class": "form-control"}),
            "flight_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "pilot_in_command": forms.TextInput(attrs={"class": "form-control"}),
            "license_number": forms.TextInput(attrs={"class": "form-control"}),

            "takeoff_latlong": forms.TextInput(attrs={"class": "form-control"}),
            "takeoff_address": forms.TextInput(attrs={"class": "form-control"}),

            "drone_name": forms.TextInput(attrs={"class": "form-control"}),
            "drone_type": forms.TextInput(attrs={"class": "form-control"}),
            "drone_serial": forms.TextInput(attrs={"class": "form-control"}),
            "drone_reg_number": forms.TextInput(attrs={"class": "form-control"}),

            "flight_application": forms.TextInput(attrs={"class": "form-control"}),
            "remote_id": forms.TextInput(attrs={"class": "form-control"}),

            "battery_name": forms.TextInput(attrs={"class": "form-control"}),
            "battery_serial_printed": forms.TextInput(attrs={"class": "form-control"}),
            "battery_serial_internal": forms.TextInput(attrs={"class": "form-control"}),

            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "tags": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        """
        Add form-control class to any fields not explicitly configured above.
        """
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
                continue
            current = w.attrs.get("class", "")
            if "form-control" not in current:
                w.attrs["class"] = (current + " form-control").strip()
