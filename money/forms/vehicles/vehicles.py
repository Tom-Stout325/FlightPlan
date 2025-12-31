from django import forms

from django.forms import inlineformset_factory

from ...models import (
        Vehicle,
        VehicleYear,
)






class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "name",
            "placed_in_service_date",
            "placed_in_service_mileage",
            "year",
            "make",
            "model",
            "plate",
            "vin",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., 2018 F-150"}),
            "placed_in_service_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "placed_in_service_mileage": forms.NumberInput(attrs={"step": "0.1", "class": "form-control"}),
            "year": forms.NumberInput(attrs={"class": "form-control", "min": "1900", "max": "2100"}),
            "make": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ford"}),
            "model": forms.TextInput(attrs={"class": "form-control", "placeholder": "F-150"}),
            "plate": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
            "vin": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class VehicleYearForm(forms.ModelForm):
    class Meta:
        model = VehicleYear
        fields = ["tax_year", "begin_mileage", "end_mileage"]
        widgets = {
            "tax_year": forms.NumberInput(attrs={"class": "form-control", "min": "2000", "max": "2100"}),
            "begin_mileage": forms.NumberInput(attrs={"step": "0.1", "class": "form-control"}),
            "end_mileage": forms.NumberInput(attrs={"step": "0.1", "class": "form-control"}),
        }


VehicleYearFormSet = inlineformset_factory(
    parent_model=Vehicle,
    model=VehicleYear,
    form=VehicleYearForm,
    extra=1,
    can_delete=True,
)

