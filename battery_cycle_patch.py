
# Add this import near the top of equipment/views.py
from django.db.models import Count, Sum, F, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce

# Replace your existing battery stats logic with this helper:

def _attach_battery_cycle_stats(request, equipment_qs):
    """
    Adds:
      - flights_count
      - estimated_cycles
      - total_discharge_percent

    Battery cycles are calculated using:
        cumulative discharge percentage / 100

    Example:
        35% + 40% + 25% = 100% = 1 cycle
    """

    battery_serials = list(
        equipment_qs.filter(equipment_type="Battery")
        .exclude(serial_number__isnull=True)
        .exclude(serial_number__exact="")
        .values_list("serial_number", flat=True)
    )

    stats_map = {}

    if battery_serials:
        flight_qs = FlightLog.objects.filter(
            battery_serial_printed__in=battery_serials
        )

        if hasattr(FlightLog, "user"):
            flight_qs = flight_qs.filter(user=request.user)

        discharge_expr = ExpressionWrapper(
            Coalesce(F("takeoff_battery_percent"), 0) -
            Coalesce(F("landing_battery_percent"), 0),
            output_field=FloatField(),
        )

        stats = (
            flight_qs
            .annotate(discharge_used=discharge_expr)
            .values("battery_serial_printed")
            .annotate(
                flights_count=Count("id"),
                total_discharge=Sum("discharge_used"),
            )
        )

        stats_map = {
            row["battery_serial_printed"]: {
                "flights_count": row["flights_count"] or 0,
                "total_discharge": row["total_discharge"] or 0,
                "estimated_cycles": round((row["total_discharge"] or 0) / 100, 1),
            }
            for row in stats
        }

    for eq in equipment_qs:
        serial = (eq.serial_number or "").strip()

        if eq.equipment_type == "Battery" and serial:
            s = stats_map.get(serial, {})
            eq.flights_count = s.get("flights_count", 0)
            eq.total_discharge = s.get("total_discharge", 0)
            eq.estimated_cycles = s.get("estimated_cycles", 0)
        else:
            eq.flights_count = 0
            eq.total_discharge = 0
            eq.estimated_cycles = 0

    return equipment_qs
