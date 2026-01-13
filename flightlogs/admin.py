# flightlogs/admin.py
from __future__ import annotations

from django.contrib import admin

from .models import FlightLog


@admin.register(FlightLog)
class FlightLogAdmin(admin.ModelAdmin):
    list_display = (
        "flight_date",
        "flight_title",
        "pilot_in_command",
        "drone_name",
        "takeoff_address",
        "air_time",
        "user",
    )

    list_filter = (
        "flight_date",
        "drone_name",
        "drone_type",
    )

    search_fields = (
        "flight_title",
        "flight_description",
        "pilot_in_command",
        "license_number",
        "drone_name",
        "drone_type",
        "drone_serial",
        "drone_reg_number",
        "takeoff_address",
        "tags",
        "notes",
    )

    ordering = ("-flight_date",)
    date_hierarchy = "flight_date"
    list_select_related = ("user",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not change or not obj.user_id:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.user_id == request.user.id

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.user_id == request.user.id

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.user_id == request.user.id
