from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Equipment, DroneSafetyProfile


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [
            "name",
            "equipment_type",
            "brand",
            "model",
            "serial_number",
            "faa_number",
            "faa_certificate",
            "receipt",
            "purchase_date",
            "purchase_cost",
            "placed_in_service_date",
            "property_type",
            "depreciation_method",
            "useful_life_years",
            "business_use_percent",
            "date_sold",
            "sale_price",
            "active",
            "notes",
            "drone_safety_profile",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "equipment_type": forms.Select(attrs={"class": "form-select"}),
            "brand": forms.TextInput(attrs={"class": "form-control"}),
            "model": forms.TextInput(attrs={"class": "form-control"}),
            "serial_number": forms.TextInput(attrs={"class": "form-control"}),
            "faa_number": forms.TextInput(attrs={"class": "form-control"}),
            "purchase_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "purchase_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "placed_in_service_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "property_type": forms.Select(attrs={"class": "form-select"}),
            "depreciation_method": forms.Select(attrs={"class": "form-select"}),
            "useful_life_years": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 50}),
            "business_use_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0, "max": 100}),
            "date_sold": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "drone_safety_profile": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        # `user` is optional; views should pass it for consistency & future scoping.
        self.user = user
        super().__init__(*args, **kwargs)

        if "drone_safety_profile" in self.fields:
            self.fields["drone_safety_profile"].queryset = (
                DroneSafetyProfile.objects.filter(active=True).order_by("brand", "model_name")
            )

        # If editing an existing non-drone item, hide drone-only fields for better UX
        equipment_type = getattr(self.instance, "equipment_type", None)
        if self.instance.pk and equipment_type and equipment_type != "Drone":
            for f in ("faa_number", "faa_certificate", "drone_safety_profile"):
                if f in self.fields:
                    self.fields[f].required = False

    def clean_faa_certificate(self):
        file = self.cleaned_data.get("faa_certificate")
        if file and hasattr(file, "content_type"):
            allowed_types = ["application/pdf", "image/jpeg", "image/png"]
            if file.content_type not in allowed_types:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return file

    def clean_receipt(self):
        file = self.cleaned_data.get("receipt")
        if file and hasattr(file, "content_type"):
            allowed_types = ["application/pdf", "image/jpeg", "image/png"]
            if file.content_type not in allowed_types:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return file

    def clean_business_use_percent(self):
        val = self.cleaned_data.get("business_use_percent")
        if val is None:
            return val
        if val < Decimal("0.00") or val > Decimal("100.00"):
            raise ValidationError("Business use percent must be between 0 and 100.")
        return val

    def clean(self):
        cleaned = super().clean()

        purchase_date = cleaned.get("purchase_date")
        placed_in_service = cleaned.get("placed_in_service_date")
        if purchase_date and not placed_in_service:
            cleaned["placed_in_service_date"] = purchase_date

        date_sold = cleaned.get("date_sold")
        sale_price = cleaned.get("sale_price")
        if date_sold and sale_price is None:
            self.add_error("sale_price", "Sale price is required when a sold date is provided.")
        if sale_price is not None and not date_sold:
            self.add_error("date_sold", "Sold date is required when a sale price is provided.")

        equipment_type = cleaned.get("equipment_type")
        if equipment_type and equipment_type != "Drone":
            if cleaned.get("faa_number"):
                self.add_error("faa_number", "FAA number is only applicable to drones.")
            if cleaned.get("faa_certificate"):
                self.add_error("faa_certificate", "FAA certificate is only applicable to drones.")
            if cleaned.get("drone_safety_profile"):
                self.add_error("drone_safety_profile", "Safety profiles are only applicable to drones.")

        return cleaned


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
            "model_name": forms.TextInput(attrs={"class": "form-control"}),
            "full_display_name": forms.TextInput(attrs={"class": "form-control"}),
            "year_released": forms.NumberInput(attrs={"class": "form-control", "min": 2000, "max": 2100}),
            "is_enterprise": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "safety_features": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "• Omnidirectional obstacle sensing – ...\n• Advanced RTH – ...",
                }
            ),
            "aka_names": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Optional alternate names, comma-separated"}
            ),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
