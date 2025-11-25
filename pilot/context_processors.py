from .models import ClientProfile

def client_profile(request):
    profile = ClientProfile.get_active()
    absolute_logo_url = None
    if profile and getattr(profile.logo, "url", None) and request:
        try:
            absolute_logo_url = request.build_absolute_uri(profile.logo.url)
        except Exception:
            absolute_logo_url = None

    return {
        "client_profile": profile,
        "client_profile_absolute_logo_url": absolute_logo_url,
    }
