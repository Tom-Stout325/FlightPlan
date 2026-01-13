# money/context_processors.py

import re
from .models import CompanyProfile


def company_profile(request):
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
        digits = re.sub(r"\D", "", profile.main_phone)
        if len(digits) == 10:
            formatted_phone = f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"
        else:
            formatted_phone = profile.main_phone

    return {
        # ✅ Primary objects
        "company_profile": profile,
        "company_name": profile.name_for_display if profile else "",

        # ✅ Branding helpers
        "COMPANY_PROFILE": profile,          # optional legacy alias
        "COMPANY_LOGO_URL": absolute_logo_url,
        "formatted_company_phone": formatted_phone,

        # ✅ Business rules / flags
        "vehicle_expense_method": getattr(profile, "vehicle_expense_method", "mileage"),
    }
