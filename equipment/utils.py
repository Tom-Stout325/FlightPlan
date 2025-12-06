# equipment/utils.py
from typing import Optional
from django.db.models import Q
from .models import DroneSafetyProfile


def find_best_drone_profile(brand: str | None, query: str) -> Optional[DroneSafetyProfile]:
    """
    Try to find the best matching DroneSafetyProfile for a brand + user-entered query.
    This is intentionally fuzzy and can be tuned over time.
    """
    if not query:
        return None

    qs = DroneSafetyProfile.objects.filter(active=True)

    if brand:
        qs = qs.filter(brand__iexact=brand)

    cleaned_query = query.strip()

    # Best-case: direct match
    direct = qs.filter(full_display_name__iexact=cleaned_query).first()
    if direct:
        return direct

    # Next: model_name exact
    exact_model = qs.filter(model_name__iexact=cleaned_query).first()
    if exact_model:
        return exact_model

    # Next: contains in display/model/aka_names
    loose = qs.filter(
        Q(full_display_name__icontains=cleaned_query)
        | Q(model_name__icontains=cleaned_query)
        | Q(aka_names__icontains=cleaned_query)
    ).first()

    return loose
