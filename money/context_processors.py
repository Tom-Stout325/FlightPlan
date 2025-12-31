from .models import CompanyProfile
import re

def client_profile(request):
    profile = CompanyProfile.get_active()

    absolute_logo_url = None
    if (
        request
        and profile
        and getattr(profile, "logo", None)
        and getattr(profile.logo, "url", None)
    ):
        try:
            absolute_logo_url = request.build_absolute_uri(profile.logo.url)
        except Exception:
            absolute_logo_url = None

    # Format phone number: (317) 987-7387
    formatted_phone = None
    if profile and profile.main_phone:
        # Remove non-digits
        digits = re.sub(r"\D", "", profile.main_phone)

        # US 10-digit format
        if len(digits) == 10:
            formatted_phone = f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"
        else:
            formatted_phone = profile.main_phone # fallback

    return {
        "BRAND_PROFILE": profile,
        "BRAND_LOGO_URL": absolute_logo_url,
        "formatted_brand_phone": formatted_phone,
         "vehicle_expense_method": getattr(profile, "vehicle_expense_method", "mileage"),
}
    
