from django.contrib import admin
from .models import *



@admin.register(OpsPlan)
class OpsPlanAdmin(admin.ModelAdmin):
    list_display = ('event', 'plan_year', 'waivers_required', 'status', 'updated_at')
    list_filter  = ('waivers_required', 'status', 'plan_year')
    search_fields = ('event_name', 'pilot_in_command', 'airport', 'address')