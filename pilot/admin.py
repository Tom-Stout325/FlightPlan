# pilot/admin.py

from django.contrib import admin

from .models import PilotProfile, Training


@admin.register(PilotProfile)
class PilotProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "license_number", "license_date")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "license_number",
    )
    list_select_related = ("user",)


@admin.register(Training)
class TrainingAdmin(admin.ModelAdmin):
    list_display = ("title", "date_completed", "required", "user", "pilot")
    list_filter = ("required", "date_completed")
    search_fields = (
        "title",
        "user__username",
        "user__first_name",
        "user__last_name",
        "pilot__user__username",
        "pilot__user__first_name",
        "pilot__user__last_name",
    )
    list_select_related = ("user", "pilot", "pilot__user")
