# project/urls_money_testers.py
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # accounts/auth routes
    path("", include(("accounts.urls", "accounts"), namespace="accounts")),

    # money routes
    path("money/", include(("money.urls", "money"), namespace="money")),
]
