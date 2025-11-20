# help/urls.py
from django.urls import path

from . import views

app_name = "help"

urlpatterns = [
    path("help/", views.help_home, name="help_home"),
    path("help/pilot-profile/", views.help_pilot_profile, name="help_pilot_profile"),
    path("help/equipment/", views.help_equipment, name="help_equipment"),
    path("help/flight-logs/", views.help_flight_logs, name="help_flight_logs"),
    path("help/documents/", views.help_documents, name="help_documents"),
    path("help/getting-started/", views.help_getting_started, name="help_getting_started"),
    path("help/gmail/", views.help_gmail, name="help_gmail"),
]
