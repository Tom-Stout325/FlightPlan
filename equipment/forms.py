from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Equipment, DroneSafetyProfile
from decimal import Decimal






class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [
            # Core
            "name",
            "equipment_type",
            "brand",
            "model",
            "serial_number",

            # Drone-only (FAA)
            "faa_number",
            "faa_certificate",
            "drone_safety_profile",

            # Purchase / sale
            "purchase_date",
            "purchase_cost",
            "receipt",
            "date_sold",
            "sale_price",

            # Tax / depreciation
            "property_type",
            "placed_in_service_date",
            "depreciation_method",
            "useful_life_years",
            "business_use_percent",
            "deducted_full_cost",

            # Other
            "notes",
            "active",
        ]

        widgets = {
            # Dates
            "purchase_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "placed_in_service_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "date_sold": forms.DateInput(attrs={"type": "date", "class": "form-control"}),

            # Text inputs
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "brand": forms.TextInput(attrs={"class": "form-control"}),
            "model": forms.TextInput(attrs={"class": "form-control"}),
            "serial_number": forms.TextInput(attrs={"class": "form-control"}),
            "faa_number": forms.TextInput(attrs={"class": "form-control"}),

            # Numbers
            "purchase_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "useful_life_years": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "business_use_percent": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "100"}
            ),

            # Selects
            "equipment_type": forms.Select(attrs={"class": "form-control"}),
            "property_type": forms.Select(attrs={"class": "form-control"}),
            "depreciation_method": forms.Select(attrs={"class": "form-control"}),
            "drone_safety_profile": forms.Select(attrs={"class": "form-control"}),

            # Textarea
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),

            # Checkboxes
            "deducted_full_cost": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only show active safety profiles
        if "drone_safety_profile" in self.fields:
            self.fields["drone_safety_profile"].queryset = (
                DroneSafetyProfile.objects.filter(active=True).order_by("brand", "model_name")
            )

        # Optional convenience: default placed_in_service_date to purchase_date for new items
        if not self.instance.pk and "placed_in_service_date" in self.fields:
            purchase = self.initial.get("purchase_date") or None
            if purchase:
                self.fields["placed_in_service_date"].initial = purchase

    # -------------------------
    # File validation
    # -------------------------
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

    # -------------------------
    # Field-level validation
    # -------------------------
    def clean_business_use_percent(self):
        val = self.cleaned_data.get("business_use_percent")
        if val is None:
            return val
        if val < Decimal("0.00") or val > Decimal("100.00"):
            raise ValidationError("Business use percent must be between 0 and 100.")
        return val

    def clean(self):
        cleaned = super().clean()

        # Keep placed-in-service default aligned with purchase date if user didn't set it
        purchase_date = cleaned.get("purchase_date")
        placed_in_service = cleaned.get("placed_in_service_date")
        if purchase_date and not placed_in_service:
            cleaned["placed_in_service_date"] = purchase_date

        # Sale pair consistency (model clean also enforces, but this gives immediate form feedback)
        date_sold = cleaned.get("date_sold")
        sale_price = cleaned.get("sale_price")
        if date_sold and sale_price is None:
            self.add_error("sale_price", "Sale price is required when a sold date is provided.")
        if sale_price is not None and not date_sold:
            self.add_error("date_sold", "Sold date is required when a sale price is provided.")

        # Drone-only enforcement at the form level (mirrors model.clean)
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
