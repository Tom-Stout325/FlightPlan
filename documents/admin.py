# documents/admin.py
from django.contrib import admin

from .models import DroneIncidentReport, SOPDocument, GeneralDocument


@admin.register(DroneIncidentReport)
class DroneIncidentReportAdmin(admin.ModelAdmin):
    list_display = ("id", "report_date", "reported_by", "event_date", "location", "user")
    list_filter = ("report_date", "event_date", "injuries", "damage", "faa_report", "user")
    search_fields = ("reported_by", "location", "description", "faa_ref", "user__username", "user__email")
    date_hierarchy = "report_date"
    ordering = ("-report_date",)
    raw_id_fields = ("user",)


@admin.register(SOPDocument)
class SOPDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "created_at")
    list_filter = ("created_at", "user")
    search_fields = ("title", "description", "user__username", "user__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    raw_id_fields = ("user",)


@admin.register(GeneralDocument)
class GeneralDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "user", "uploaded_at")
    list_filter = ("category", "uploaded_at", "user")
    search_fields = ("title", "description", "category", "user__username", "user__email")
    date_hierarchy = "uploaded_at"
    ordering = ("-uploaded_at",)
    raw_id_fields = ("user",)
