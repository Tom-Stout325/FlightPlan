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
        "year_released",
        "is_enterprise",
        "active",
    )
    list_filter = ("brand", "active", "is_enterprise")
    search_fields = ("full_display_name", "model_name", "aka_names", "safety_features")
