import csv
import re
import tempfile
from datetime import datetime, timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_exempt
from django.db.models import Count
import re
from calendar import month_name
from django.db.models.functions import ExtractYear, ExtractMonth
from urllib.parse import urlencode

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False


from .models import (
    FlightLog,
)
from .forms import (
    FlightLogCSVUploadForm,
)


STATE_RE = re.compile(r",\s*([A-Z]{2})(?:[, ]|$)")


def safe_int(value):
    """Parse an int from mixed strings like '85%', ' 1,234 ', or None."""
    try:
        if value is None:
            return None
        s = re.sub(r'[^0-9\-]+', '', str(value))
        return int(s) if s not in ("", "-", None, "") else None
    except Exception:
        return None

def safe_float(value):
    """Parse a float from mixed strings like '1,234.56 mph', or None."""
    try:
        if value is None:
            return None
        s = re.sub(r'[^0-9\.\-]+', '', str(value))
        return float(s) if s not in ("", "-", ".", None) else None
    except Exception:
        return None

def safe_pct(value):
    """Parse a percent value that may contain '%' or whitespace."""
    return safe_int(str(value).replace('%', '')) if value is not None else None

def extract_state(address):
    """Pull a 2-letter state abbreviation from addresses like 'City, ST, USA'."""
    match = re.search(r",\s*([A-Z]{2})[, ]", address or "")
    return match.group(1) if match else None



def _extract_state(addr: str | None) -> str | None:
    if not addr:
        return None
    m = STATE_RE.search(addr)
    return m.group(1) if m else None

def _extract_city(addr: str | None) -> str | None:
    """
    Very simple 'City, ST ...' parser: returns text before first comma.
    """
    if not addr:
        return None
    city = addr.split(",", 1)[0].strip()
    # Ignore empty or obviously non-city tokens
    return city or None



@login_required
def drone_portal(request):
    """
    Main Drone Portal dashboard: cards/links for flight logs, maps,
    equipment, documents, etc.
    """
    return render(request, "flightlogs/drone_portal.html")


@login_required
def flightlog_list(request):
    # --- Read filters (as strings) ---
    sel_state = request.GET.get("state", "").strip() or ""
    sel_city  = request.GET.get("city", "").strip() or ""
    sel_year  = request.GET.get("year", "").strip() or ""
    sel_month = request.GET.get("month", "").strip() or ""  # 1..12

    logs_qs = FlightLog.objects.all()

    # --- Build filter options efficiently ---
    # Years & months from DB (fast; uses functions)
    year_rows = (
        FlightLog.objects.annotate(y=ExtractYear("flight_date"))
        .values_list("y", flat=True)
        .distinct()
    )
    years = sorted(y for y in year_rows if y)

    month_rows = (
        FlightLog.objects.annotate(m=ExtractMonth("flight_date"))
        .values_list("m", flat=True)
        .distinct()
    )
    months_present = sorted(m for m in month_rows if m)

    # States/cities derived from takeoff_address (1700 rows is fine)
    # Pull only the column we need to minimize memory
    addresses = list(
        FlightLog.objects
        .exclude(takeoff_address__exact="")
        .values_list("takeoff_address", flat=True)
    )

    states_set: set[str] = set()
    # If a state is selected, only compute cities for that state
    cities_set: set[str] = set()
    for addr in addresses:
        st = _extract_state(addr)
        if not st:
            continue
        states_set.add(st)
        if sel_state and st != sel_state:
            continue
        city = _extract_city(addr)
        if city:
            cities_set.add(city)

    states = sorted(states_set)
    cities = sorted(cities_set) if sel_state else sorted({c for a in addresses if (c := _extract_city(a))})

    # --- Apply filters to queryset ---
    if sel_year.isdigit():
        logs_qs = logs_qs.filter(flight_date__year=int(sel_year))

    if sel_month.isdigit():
        logs_qs = logs_qs.filter(flight_date__month=int(sel_month))

    # For state/city we must parse in Python; do a coarse prefilter on address where possible
    if sel_state:
        logs_qs = logs_qs.filter(takeoff_address__icontains=f", {sel_state}")

    if sel_city:
        logs_qs = logs_qs.filter(takeoff_address__istartswith=sel_city)

    logs_qs = logs_qs.order_by("-flight_date")

    # --- Pagination (preserve GET params) ---
    paginator = Paginator(logs_qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Build a querystring without 'page' so pagers can append page=...
    qs = request.GET.copy()
    qs.pop("page", None)
    qs_without_page = qs.urlencode()

    # Month label map for template
    month_labels = {m: month_name[m] for m in range(1, 13)}

    context = {
        "logs": page_obj,
        "current_page": "flightlogs",

        # Selected values
        "sel_state": sel_state,
        "sel_city": sel_city,
        "sel_year": sel_year,
        "sel_month": sel_month,

        # Options
        "states": states,
        "cities": cities,
        "years": years,
        "months_present": months_present,
        "month_labels": month_labels,

        # For pagination links
        "qs_without_page": qs_without_page,
    }
    return render(request, "flightlogs/flightlog_list.html", context)


@login_required
def export_flightlogs_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="flight_logs.csv"'
    writer = csv.writer(response)

    fields = [f.name for f in FlightLog._meta.fields]
    writer.writerow(fields)

    for log in FlightLog.objects.all().order_by('-flight_date'):
        writer.writerow([getattr(log, name) for name in fields])

    return response



@login_required
def flightlog_detail(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    context = {'log': log, 'current_page': 'flightlogs'}
    return render(request, 'flightlogs/flightlog_detail.html', context)



@login_required
def flightlog_edit(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    # NOTE: Consider a dedicated FlightLogForm for editing instead of the CSV upload form.
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            messages.success(request, 'Flight log updated.')
            return redirect('flightlog_list')
        messages.error(request, 'There was a problem updating the flight log.')
    else:
        form = FlightLogCSVUploadForm(instance=log)

    return render(request, 'flightlogs/flightlog_form.html', {'form': form, 'log': log, 'current_page': 'flightlogs'})


@login_required
def flightlog_business(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            messages.success(request, 'Flight log updated.')
            return redirect('flightlog_list')
        messages.error(request, 'There was a problem updating the flight log.')
    else:
        form = FlightLogCSVUploadForm(instance=log)

    return render(request, 'flightlogs/flightlog_form.html', {'form': form, 'log': log, 'current_page': 'flightlogs'})


@login_required
def flightlog_delete(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    if request.method == 'POST':
        title = log.flight_title or f'Log {pk}'
        log.delete()
        messages.success(request, f'{title} deleted.')
        return redirect('flightlog_list')
    return render(request, 'flightlogs/flightlog_confirm_delete.html', {'log': log, 'current_page': 'flightlogs'})


@login_required
def flightlog_pdf(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    context = {'log': log, 'current_page': 'flightlogs'}
    html_string = render_to_string('flightlogs/flightlog_detail_pdf.html', context)
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_file:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(tmp_file.name)
        tmp_file.seek(0)
        response = HttpResponse(tmp_file.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="FlightLog_{log.pk}.pdf"'
        return response


# -------------------------------------------------
# F L I G H T   L O G   C S V   U P L O A D
# -------------------------------------------------
@login_required
def upload_flightlog_csv(request):
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['csv_file']
            decoded = file.read().decode('utf-8-sig').splitlines()
            reader = csv.DictReader(decoded)
            reader.fieldnames = [field.strip().replace('\ufeff', '') for field in reader.fieldnames]

            # Header alias mapping
            field_aliases = {"Flight/Service Date": "Flight Date/Time"}

            created = 0
            skipped = 0
            errored = 0

            for raw_row in reader:
                # Normalize column keys & values
                row = {
                    field_aliases.get(k.strip(), k.strip()): (v.strip() if v else "")
                    for k, v in raw_row.items()
                }

                # Require a date/time
                if not row.get("Flight Date/Time"):
                    skipped += 1
                    continue

                # Parse datetime
                try:
                    clean_dt = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', row["Flight Date/Time"])
                    dt = datetime.strptime(clean_dt, "%b %d, %Y %I:%M%p")
                except Exception:
                    skipped += 1
                    continue

                flight_date = dt.date()
                landing_time = dt.time()

                try:
                    air_seconds = safe_int(row.get("Air Seconds")) or 0
                    air_time = timedelta(seconds=air_seconds)

                    FlightLog.objects.create(
                        flight_date=flight_date,
                        flight_title=row.get("Flight Title", ""),
                        flight_description=row.get("Flight Description", ""),
                        pilot_in_command=row.get("Pilot-in-Command", ""),
                        license_number=row.get("License Number", ""),
                        takeoff_latlong=row.get("Takeoff Lat/Long", ""),
                        takeoff_address=row.get("Takeoff Address", ""),
                        landing_time=landing_time,
                        air_time=air_time,
                        above_sea_level_ft=safe_float(row.get("Above Sea Level (Feet)")),
                        drone_name=row.get("Drone Name", ""),
                        drone_type=row.get("Drone Type", ""),
                        drone_serial=row.get("Drone Serial Number", ""),
                        drone_reg_number=row.get("Drone Registration Number", ""),
                        flight_application=row.get("Flight App", ""),
                        remote_id=row.get("Remote ID", ""),
                        battery_name=row.get("Battery Name", ""),
                        battery_serial_printed=row.get("Bat Printed Serial", ""),
                        battery_serial_internal=row.get("Bat Internal Serial", ""),
                        takeoff_battery_pct=safe_pct(row.get("Takeoff Bat %")),
                        takeoff_mah=safe_int(row.get("Takeoff mAh")),
                        takeoff_volts=safe_float(row.get("Takeoff Volts")),
                        landing_battery_pct=safe_pct(row.get("Landing Bat %")),
                        landing_mah=safe_int(row.get("Landing mAh")),
                        landing_volts=safe_float(row.get("Landing Volts")),
                        max_altitude_ft=safe_float(row.get("Max Altitude (Feet)")),
                        max_distance_ft=safe_float(row.get("Max Distance (Feet)")),
                        max_battery_temp_f=safe_float(row.get("Max Bat Temp (f)")),
                        max_speed_mph=safe_float(row.get("Max Speed (mph)")),
                        total_mileage_ft=safe_float(row.get("Total Mileage (Feet)")),
                        signal_score=safe_float(row.get("Signal Score")),
                        max_compass_rate=safe_float(row.get("Max Compass Rate")),
                        avg_wind=safe_float(row.get("Avg Wind")),
                        max_gust=safe_float(row.get("Max Gust")),
                        signal_losses=safe_int(row.get("Signal Losses (>1 sec)")),
                        ground_weather_summary=row.get("Ground Weather Summary", ""),
                        ground_temp_f=safe_float(row.get("Ground Temperature (f)")),
                        visibility_miles=safe_float(row.get("Ground Visibility (Miles)")),
                        wind_speed=safe_float(row.get("Ground Wind Speed")),
                        wind_direction=row.get("Ground Wind Direction", ""),
                        cloud_cover=safe_pct(row.get("Cloud Cover")),
                        humidity_pct=safe_pct(row.get("Humidity")),
                        dew_point_f=safe_float(row.get("Dew Point (f)")),
                        pressure_inhg=safe_float(row.get("Pressure")),
                        rain_rate=row.get("Rain Rate", ""),
                        rain_chance=row.get("Rain Chance", ""),
                        sunrise=row.get("Sunrise", ""),
                        sunset=row.get("Sunset", ""),
                        moon_phase=row.get("Moon Phase", ""),
                        moon_visibility=row.get("Moon Visibility", ""),
                        photos=safe_int(row.get("Photos")),
                        videos=safe_int(row.get("Videos")),
                        notes=row.get("Add Additional Notes", ""),
                        tags=row.get("Tags", ""),
                    )
                    created += 1
                except Exception as e:
                    # Keep importing; log the row for review
                    errored += 1
                    print("Row error:", e, raw_row)

            messages.success(request, f"Flight log CSV processed. Created: {created}, Skipped: {skipped}, Errors: {errored}")
            return redirect('flightlog_list')
        else:
            messages.error(request, "Invalid form submission.")
    else:
        form = FlightLogCSVUploadForm()

    # Render upload page on GET or invalid POST
    return render(request, 'flightlogs/flightlog_form.html', {'form': form, 'current_page': 'flightlogs'})


# -------------------------------------------------
# M A P S
# -------------------------------------------------


@login_required
def flight_map_view(request):
    logs = FlightLog.objects.all().order_by('-flight_date')[:100]
    locations_qs = (
        FlightLog.objects
        .values('takeoff_latlong', 'takeoff_address')
        .annotate(count=Count('id'))
        .exclude(takeoff_latlong__exact="")
        .order_by('takeoff_address')
    )
    locations = list(locations_qs)

    states = set()
    cities = set()
    for loc in locations:
        addr = loc.get("takeoff_address", "")
        if addr:
            cities.add(addr.strip())
            state = extract_state(addr)
            if state:
                states.add(state)

    context = {
        'locations': locations,
        'num_states': len(states),
        'num_cities': len(cities),
        'logs': logs,
    }
    return render(request, 'flightlogs/map.html', context)


@xframe_options_exempt
def flight_map_embed(request):
    locations_qs = (
        FlightLog.objects
        .values('takeoff_latlong', 'takeoff_address')
        .annotate(count=Count('id'))
        .exclude(takeoff_latlong__exact="")
    )
    locations = list(locations_qs)

    states = set()
    cities = set()
    for loc in locations:
        addr = loc.get("takeoff_address", "")
        if addr:
            cities.add(addr.strip())
            state = extract_state(addr)
            if state:
                states.add(state)

    context = {
        'locations': locations,
        'num_states': len(states),
        'num_cities': len(cities),
    }
    return render(request, 'flightlogs/map_embed.html', context)

