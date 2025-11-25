from django.conf import settings


def brand_context(request):
    """
    Inject per-client branding + feature flags into all templates.
    """
    return {
        "BRAND_NAME": getattr(settings, "BRAND_NAME", "Airborne Images"),
        "BRAND_TAGLINE": getattr(settings, "BRAND_TAGLINE", ""),
        "CLIENT": getattr(settings, "CLIENT", None),
        "CLIENT_SLUG": getattr(settings, "CLIENT_SLUG", None),
        "CLIENT_FEATURES": getattr(settings, "CLIENT_FEATURES", {}),
    }
