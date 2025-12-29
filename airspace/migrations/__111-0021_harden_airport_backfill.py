from __future__ import annotations

import re
from decimal import Decimal
from math import atan2, cos, radians, sin, sqrt

from django.db import migrations


NM_PER_KM = Decimal("0.539956803")
EARTH_RADIUS_KM = Decimal("6371.0088")

ICAO_RE = re.compile(r"\b([A-Z]{4})\b")


def normalize_icao(value: str | None) -> str:
    """
    Same normalizer as 0018; keeps behavior consistent.
    """
    s = (value or "").strip().upper()
    if not s:
        return ""
    m = ICAO_RE.search(s)
    return m.group(1) if m else s


def haversine_nm(lat1, lon1, lat2, lon2) -> Decimal:
    phi1 = radians(float(lat1))
    phi2 = radians(float(lat2))
    dphi = radians(float(lat2 - lat1))
    dlambda = radians(float(lon2 - lon1))

    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    km = Decimal(str(float(EARTH_RADIUS_KM) * c))
    return (km * NM_PER_KM).quantize(Decimal("0.01"))


def forwards(apps, schema_editor):
    WaiverPlanning = apps.get_model("airspace", "WaiverPlanning")
    Airport = apps.get_model("airspace", "Airport")

    # Only backfill rows still missing FK
    rows = (
        WaiverPlanning.objects
        .filter(nearest_airport_ref_id__isnull=True)
        .exclude(nearest_airport__isnull=True)
        .exclude(nearest_airport="")
        .values_list(
            "id",
            "nearest_airport",
            "location_latitude",
            "location_longitude",
        )
        .iterator(chunk_size=2000)
    )

    # Cache ICAO -> (id, lat, lon) to reduce DB hits
    airport_cache: dict[str, tuple[int, Decimal | None, Decimal | None]] = {}

    for wp_id, nearest_airport, lat, lon in rows:
        code = normalize_icao(nearest_airport)
        if not code:
            continue

        if code not in airport_cache:
            airport = (
                Airport.objects
                .filter(icao=code, active=True)
                .values_list("id", "latitude", "longitude")
                .first()
            )
            if not airport:
                airport_cache[code] = (0, None, None)  # sentinel for "not found"
            else:
                airport_cache[code] = airport

        airport_id, a_lat, a_lon = airport_cache[code]
        if not airport_id:
            continue

        update_kwargs = {"nearest_airport_ref_id": airport_id}

        if lat is not None and lon is not None and a_lat is not None and a_lon is not None:
            update_kwargs["distance_to_airport_nm"] = haversine_nm(lat, lon, a_lat, a_lon)

        WaiverPlanning.objects.filter(id=wp_id).update(**update_kwargs)


def backwards(apps, schema_editor):
    """
    No-op on purpose.
    This is a repair/hardening migration; reversing would be surprising.
    """
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("airspace", "0020_alter_waiverplanning_options"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
