# project/urls_money_testers.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import home as accounts_home


urlpatterns = [
    path("admin/", admin.site.urls),

    # Home page (same entry point, but money-focused environment)
    path("", accounts_home, name="home"),

    # Money app
    path("money/", include(("money.urls", "money"), namespace="money")),

    # Accounts (login / logout / register / profile)
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
]

# Media handling (same logic as main urls.py)
if settings.DEBUG and not getattr(settings, "USE_S3", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
