from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import *




class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [ 
            'name', 'equipment_type', 'brand', 'model', 'serial_number',
            'faa_number', 'faa_certificate', 'purchase_date', 'purchase_cost',
            'receipt', 'date_sold', 'sale_price', 'deducted_full_cost',
            'notes', 'active'
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
