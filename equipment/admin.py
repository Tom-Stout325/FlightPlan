from django.contrib import admin
from .models import *
from .forms import EquipmentForm
from .models import DroneSafetyProfile



@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    form = EquipmentForm
    list_display = ['id', 'name', 'active']





@admin.register(DroneSafetyProfile)
class DroneSafetyProfileAdmin(admin.ModelAdmin):
    list_display = (
        "full_display_name",
        "brand",
        "released_year",
        "active",
    )
    list_filter = ("brand", "active", "released_year")
    search_fields = (
        "full_display_name",
        "model_name",
        "aka_names",
        "safety_features",
    )
    ordering = ("brand", "model_name")
    list_editable = ("active",)  

    fieldsets = (
        ("Basic Info", {
            "fields": ("brand", "model_name", "full_display_name", "active"),
        }),
        ("Timeline", {
            "fields": ("released_year", "discontinued_year"),
        }),
        ("Names / Aliases", {
            "fields": ("aka_names",),
        }),
        ("Safety & Notes", {
            "fields": ("safety_features", "notes"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    readonly_fields = ("created_at", "updated_at")
