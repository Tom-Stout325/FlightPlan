from django.contrib import admin
from .models import *
from .forms import EquipmentForm



@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    form = EquipmentForm
    list_display = ['id', 'name', 'active']



@admin.register(DroneSafetyProfile)
class DroneSafetyProfileAdmin(admin.ModelAdmin):
    list_display = (
        "full_display_name",
        "brand",
        "is_enterprise",
        "year_released",
        "active",
    )
    list_filter = ("brand", "is_enterprise", "active")
    search_fields = ("full_display_name", "model_name", "aka_names")