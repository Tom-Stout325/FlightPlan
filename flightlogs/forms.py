from django import forms
from .models import *



class FlightLogCSVUploadForm(forms.Form):
    csv_file = forms.FileField(label="Upload Flight Log CSV", widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))


