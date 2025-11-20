from django import forms
from .models import DroneIncidentReport
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import *


#<---------------------------------------- INCIDENT REPORT FORM ---------------------------------------->

class GeneralInfoForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['report_date', 'reported_by', 'contact', 'role']
        widgets = {
            'report_date': forms.DateInput(attrs={'type': 'date'}),
        }

class EventDetailsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['event_date', 'event_time', 'location', 'event_type', 'description',
                  'injuries', 'injury_details', 'damage', 'damage_cost', 'damage_desc']
        widgets = {
            'event_date': forms.DateInput(attrs={'type': 'date'}),
            'event_time': forms.TimeInput(attrs={'type': 'time'}),
        }

class EquipmentDetailsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['drone_model', 'registration', 'controller', 'payload', 'battery', ]

class EnvironmentalConditionsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['weather', 'wind', 'temperature', 'lighting']

class WitnessForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['witnesses', 'witness_details']

class ActionTakenForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['emergency', 'agency_response', 'scene_action', 'faa_report', 'faa_ref']

class FollowUpForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['cause', 'notes', 'signature', 'sign_date']
        widgets = {
            'sign_date': forms.DateInput(attrs={'type': 'date'}),
        }


#<---------------------------------------- GENERAL DOCs/SOP FORMS / SOPs ------------------------------->


class SOPDocumentForm(forms.ModelForm):
    class Meta:
        model = SOPDocument
        fields = ['title', 'description', 'file']


class GeneralDocumentForm(forms.ModelForm):
    class Meta:
        model = GeneralDocument
        fields = ['title', 'category', 'description', 'file']


