from django.contrib import admin
from .models import *
from .forms import EquipmentForm
from .models import DroneSafetyProfile




@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "equipment_type", "brand", "model", "active")
    list_filter = ("equipment_type", "active", "property_type")
    search_fields = ("name", "brand", "model", "serial_number", "faa_number")

    fieldsets = (
        ("Core", {
            "fields": (
                "name", "equipment_type", "brand", "model", "serial_number",
                "active", "notes",
            )
        }),
        ("Purchase / Sale", {
            "fields": (
                "purchase_date", "purchase_cost", "receipt",
                "date_sold", "sale_price",
            )
        }),
        ("Tax / Depreciation", {
            "fields": (
                "property_type",
                "placed_in_service_date",
                "depreciation_method",
                "useful_life_years",
                "business_use_percent",
                "deducted_full_cost",
            )
        }),
        ("Drone-only (FAA)", {
            "fields": (
                "faa_number", "faa_certificate", "drone_safety_profile",
            )
        }),
    )



@admin.register(DroneSafetyProfile)
class DroneSafetyProfileAdmin(admin.ModelAdmin):
    list_display = (
        "full_display_name",
        "brand",
        "year_released",
        "is_enterprise",
        "active",
    )
    list_filter = ("brand", "active", "is_enterprise")
    search_fields = ("full_display_name", "model_name", "aka_names", "safety_features")
