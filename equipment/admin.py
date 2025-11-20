from django.contrib import admin
from .models import *
from .forms import EquipmentForm



@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    form = EquipmentForm
    list_display = ['id', 'name', 'active']
