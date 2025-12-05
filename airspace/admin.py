# airspace/admin.py
from django.contrib import admin
from .models import AirspaceWaiver


@admin.register(AirspaceWaiver)
class AirspaceWaiverAdmin(admin.ModelAdmin):
    list_display = (
        "operation_title",
        "user",
        "nearest_airport",
        "airspace_class",
        "start_date",
        "end_date",
        "status",
        "created_at",
    )
    list_filter = ("airspace_class", "status", "nearest_airport", "created_at")
    search_fields = ("operation_title", "proposed_location", "nearest_airport")
