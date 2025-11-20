from django.conf import settings


def brand_context(request):
    """
    Inject per-client branding + feature flags into all templates.
    Values come from project.settings._client and are activated by 
    suite.py or flightplan.py depending on environment.
    """

    return {
        # Full BRAND dict (optional, useful for custom templates)
        "BRAND": getattr(settings, "BRAND", {}),

        # Common scalar convenience variables
        "BRAND_NAME": getattr(settings, "BRAND_NAME", "Airborne Images"),
        "BRAND_TAGLINE": getattr(settings, "BRAND_TAGLINE", ""),

        # Active client identifier (airborne, skyguy, demo)
        "CLIENT": getattr(settings, "CURRENT_CLIENT", None),
        "CLIENT_SLUG": getattr(settings, "CLIENT_SLUG", None),

        # Feature flags for conditional UI (e.g., NHRA = True/False)
        "CLIENT_FEATURES": getattr(settings, "CLIENT_FEATURES", {}),
    }
