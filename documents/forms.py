from __future__ import annotations

from django import forms

from .models import DroneIncidentReport, GeneralDocument, SOPDocument


# ----------------------------
# Incident Wizard Step Forms
# ----------------------------
class GeneralInfoForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["report_date", "reported_by", "contact", "role"]
        widgets = {"report_date": forms.DateInput(attrs={"type": "date"})}


class EventDetailsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["event_date", "event_time", "location", "event_type", "description"]
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "event_time": forms.TimeInput(attrs={"type": "time"}),
        }


class ImpactForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["injuries", "injury_details", "damage", "damage_cost", "damage_desc"]


class EquipmentDetailsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["drone_model", "registration", "controller", "payload", "battery"]


class EnvironmentalConditionsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["weather", "wind", "temperature", "lighting"]


class WitnessForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["witnesses", "witness_details"]


class ResponseForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["emergency", "agency_response", "scene_action", "faa_report", "faa_ref"]


class RootCauseForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["cause", "notes"]


class SignatureForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ["signature", "sign_date"]
        widgets = {"sign_date": forms.DateInput(attrs={"type": "date"})}


# ----------------------------
# SOP + General Documents
# ----------------------------
class SOPDocumentForm(forms.ModelForm):
    class Meta:
        model = SOPDocument
        fields = ["title", "description", "file"]


class GeneralDocumentForm(forms.ModelForm):
    class Meta:
        model = GeneralDocument
        fields = ["title", "category", "description", "file"]
