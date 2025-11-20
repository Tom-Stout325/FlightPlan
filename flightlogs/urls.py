# flightlogs/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views

app_name = "flightlogs"

urlpatterns = [
    path("flightlogs/", views.flightlog_list, name="flightlog_list"),
    path("flight-upload/", views.upload_flightlog_csv, name="flightlog_upload"),
    path("flightlogs/<int:pk>/", views.flightlog_detail, name="flightlog_detail"),
    path("flightlogs/<int:pk>/edit/", views.flightlog_edit, name="flightlog_edit"),
    path("flightlogs/<int:pk>/delete/", views.flightlog_delete, name="flightlog_delete"),
    path("flightlogs/<int:pk>/pdf/", views.flightlog_pdf, name="flightlog_pdf"),
    path("flightlogs/export/csv/", views.export_flightlogs_csv, name="export_flightlogs_csv"),
    path("map/", views.flight_map_view, name="flight_map"),
    path("map/embed/", views.flight_map_embed, name="flight_map_embed"),
    path("drone-portal/", views.drone_portal, name="drone_portal"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
