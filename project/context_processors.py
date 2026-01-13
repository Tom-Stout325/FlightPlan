from django.conf import settings


def tenant_context(request):
    return {
        "CLIENT": getattr(settings, "CLIENT", None),
        "CLIENT_SLUG": getattr(settings, "CLIENT_SLUG", None),
        "CLIENT_FEATURES": getattr(settings, "CLIENT_FEATURES", {}),
        "ENABLED_REPORTS": getattr(settings, "ENABLED_REPORTS", None),
    }
