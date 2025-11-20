# project/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import home as accounts_home


urlpatterns = [
 
    path("admin/", admin.site.urls),
    path("", accounts_home, name="home"),
    path("", include(("help.urls", "help"), namespace="help")),
    path("", include(("operations.urls", "operations"), namespace="operations")),
    path("", include(("flightlogs.urls", "flightlogs"), namespace="flightlogs")),
    path("", include(("documents.urls", "documents"), namespace="documents")),
    path("", include(("equipment.urls", "equipment"), namespace="equipment")),
    path("", include(("pilot.urls", "pilot"), namespace="pilot")),


    path("money/", include(("money.urls", "money"), namespace="money")),

    path("accounts/", include("accounts.urls", namespace="accounts")),
]

if settings.DEBUG and not getattr(settings, "USE_S3", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
