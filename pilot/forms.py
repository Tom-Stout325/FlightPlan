from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import *
import os



class PilotProfileForm(forms.ModelForm):
    class Meta:
        model = PilotProfile
        fields = ["license_number", "license_date", "license_image"]
        widgets = {
            "license_date": forms.DateInput(attrs={"type": "date"}),
            "license_image": forms.ClearableFileInput(
                attrs={"accept": ".pdf,.png,.jpg,.jpeg"}
            ),
        }

    def clean_license_image(self):
        file = self.cleaned_data.get("license_image")

        # No new file uploaded (keep existing one)
        if not file:
            return file

        # Check by file extension instead of MIME only
        ext = os.path.splitext(file.name)[1].lower()  # ".jpg", ".jpeg", ".png", ".pdf"
        allowed_exts = {".pdf", ".png", ".jpg", ".jpeg"}

        if ext not in allowed_exts:
            raise forms.ValidationError(
                "File type must be PDF, PNG, JPG or JPEG."
            )

        # Optional: be a bit stricter for PDFs only
        if ext == ".pdf":
            content_type = getattr(file, "content_type", "")
            if content_type != "application/pdf":
                raise forms.ValidationError("Uploaded PDF file is invalid.")

        return file



class TrainingForm(forms.ModelForm):
    class Meta:
        model = Training
        fields = ['title', 'date_completed', 'required', 'certificate']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'date_completed': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'certificate': forms.ClearableFileInput(attrs={'accept': '.pdf,.png,.jpg,.jpeg'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_certificate(self):
        file = self.files.get('certificate')  # Only look at uploaded files
        if file:
            allowed_types = ['application/pdf', 'image/png', 'image/jpeg']
            if file.content_type not in allowed_types:
                raise forms.ValidationError("Certificate must be a PDF, PNG, JPG, or JPEG.")
        return self.cleaned_data.get('certificate')
