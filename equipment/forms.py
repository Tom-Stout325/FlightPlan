from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Equipment, DroneSafetyProfile




class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [ 
            'name', 'equipment_type', 'brand', 'model', 'serial_number',
            'faa_number', 'faa_certificate', 'purchase_date', 'purchase_cost',
            'receipt', 'date_sold', 'sale_price', 'deducted_full_cost',
            'notes', 'active', 'drone_safety_profile'
        ]
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_sold': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'brand': forms.TextInput(attrs={'class': 'form-control'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'faa_number': forms.TextInput(attrs={'class': 'form-control'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control'}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'equipment_type': forms.Select(attrs={'class': 'form-control'}),
            'deducted_full_cost': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if 'drone_safety_profile' in self.fields:
                self.fields['drone_safety_profile'].queryset = (
                    DroneSafetyProfile.objects.filter(active=True).order_by("brand", "model_name")
                )

    def clean_faa_certificate(self):
        file = self.cleaned_data.get('faa_certificate')
        if file and hasattr(file, 'content_type'):
            allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
            if file.content_type not in allowed_types:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return file

    def clean_receipt(self):
        file = self.cleaned_data.get('receipt')
        if file and hasattr(file, 'content_type'):
            allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
            if file.content_type not in allowed_types:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return file



class DroneSafetyProfileForm(forms.ModelForm):
    class Meta:
        model = DroneSafetyProfile
        fields = [
            "brand",
            "model_name",
            "full_display_name",
            "year_released",
            "is_enterprise",
            "safety_features",
            "aka_names",
            "active",
        ]
        widgets = {
            "brand": forms.Select(attrs={"class": "form-select"}),
            "model_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Mavic 4 Pro"}
            ),
            "full_display_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "DJI Mavic 4 Pro"}
            ),
            "year_released": forms.NumberInput(
                attrs={"class": "form-control", "min": 2000, "max": 2100}
            ),
            "is_enterprise": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "safety_features": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "• Omnidirectional obstacle sensing – ...\n• Advanced RTH – ...",
                }
            ),
            "aka_names": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Optional alternate names, comma-separated",
                }
            ),
            "active": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }
