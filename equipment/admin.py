from django.contrib import admin
from .models import DroneSafetyProfile, Equipment



@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    search_fields = ("brand", "model", "serial_number", "faa_number")
    list_display = ("id", "brand", "model", "equipment_type", "user")
    list_filter = ("equipment_type",)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if request.user.is_superuser and "user" not in fields:
            fields.insert(0, "user")
        return fields

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            ro.append("user")
        return ro

    def save_model(self, request, obj, form, change):
        # Default owner when missing
        if not obj.user_id:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)



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
