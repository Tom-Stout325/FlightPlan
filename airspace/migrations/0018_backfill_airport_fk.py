from __future__ import annotations

from decimal import Decimal
from math import radians, sin, cos, sqrt, atan2

from django.db import migrations


NM_PER_KM = Decimal("0.539956803")
EARTH_RADIUS_KM = Decimal("6371.0088")


def haversine_nm(lat1, lon1, lat2, lon2) -> Decimal:
    # math trig requires float; result returned as Decimal
    phi1 = radians(float(lat1))
    phi2 = radians(float(lat2))
    dphi = radians(float(lat2 - lat1))
    dlambda = radians(float(lon2 - lon1))

    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    km = Decimal(str(float(EARTH_RADIUS_KM) * c))
    nm = (km * NM_PER_KM).quantize(Decimal("0.01"))
    return nm


def forwards(apps, schema_editor):
    WaiverPlanning = apps.get_model("airspace", "WaiverPlanning")
    Airport = apps.get_model("airspace", "Airport")

    # only rows where legacy nearest_airport is set and FK not already set
    qs = WaiverPlanning.objects.exclude(nearest_airport__isnull=True).exclude(nearest_airport="")

    for p in qs.iterator():
        if getattr(p, "nearest_airport_ref_id", None):
            continue

        code = (getattr(p, "nearest_airport", "") or "").strip().upper()
        if not code:
            continue

        airport = Airport.objects.filter(icao=code).first()
        if not airport:
            continue

        p.nearest_airport_ref_id = airport.id

        # compute distance if we have planning coords and airport coords
        if (
            p.location_latitude is not None
            and p.location_longitude is not None
            and airport.latitude is not None
            and airport.longitude is not None
        ):
            p.distance_to_airport_nm = haversine_nm(
                p.location_latitude,
                p.location_longitude,
                airport.latitude,
                airport.longitude,
            )

        p.save(update_fields=["nearest_airport_ref", "distance_to_airport_nm"])


def backwards(apps, schema_editor):
    WaiverPlanning = apps.get_model("airspace", "WaiverPlanning")
    WaiverPlanning.objects.update(nearest_airport_ref=None, distance_to_airport_nm=None)


class Migration(migrations.Migration):
    dependencies = [
        ("airspace", "0017_waiverplanning_distance_to_airport_nm_and_more"), 
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
