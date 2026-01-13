import csv
import tempfile
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.templatetags.static import static
from django.views.decorators.http import require_GET

from .utils import find_best_drone_profile
from flightlogs.models import FlightLog
from .models import Equipment, DroneSafetyProfile
from .forms import EquipmentForm, DroneSafetyProfileForm

try:
    from weasyprint import HTML, CSS

    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _equipment_queryset(user):
    """
    Central place to define inventory ordering + user scoping.
    """
    return (
        Equipment.objects.filter(user=user)
        .order_by("-active", "-purchase_date", "equipment_type", "name")
    )


def _attach_drone_flight_stats(request, equipment_qs):
    """
    Adds:
      - flights_count
      - total_duration
    for drone items that have serial_number.

    NOTE: If FlightLog is user-owned in your system, scope it:
      FlightLog.objects.filter(user=request.user, drone_serial__in=[...])
    """
    drone_serials = list(
        equipment_qs.filter(equipment_type="Drone")
        .exclude(serial_number__isnull=True)
        .exclude(serial_number__exact="")
        .values_list("serial_number", flat=True)
    )

    stats_map = {}
    if drone_serials:
        flight_qs = FlightLog.objects.filter(drone_serial__in=drone_serials)

        # If FlightLog has `user`, scope it. Safe no-op if it doesn't.
        if hasattr(FlightLog, "user"):
            flight_qs = flight_qs.filter(user=request.user)

        stats = (
            flight_qs.values("drone_serial")
            .annotate(
                flights_count=Count("id"),
                total_duration=Sum("flight_duration"),
            )
        )
        stats_map = {
            row["drone_serial"]: {
                "flights_count": row["flights_count"] or 0,
                "total_duration": row["total_duration"] or 0,
            }
            for row in stats
        }

    for eq in equipment_qs:
        serial = (eq.serial_number or "").strip()
        if eq.equipment_type == "Drone" and serial:
            s = stats_map.get(serial, {})
            eq.flights_count = s.get("flights_count", 0)
            eq.total_duration = s.get("total_duration", 0)
        else:
            eq.flights_count = 0
            eq.total_duration = 0

    return equipment_qs


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).strip("_") or "file"


# -------------------------------------------------------------------
# Equipment list + create (inline)
# -------------------------------------------------------------------
@login_required
def equipment_list(request):
    """
    Inventory list + inline create form.
    """
    equipment_qs = _equipment_queryset(request.user)
    equipment = _attach_drone_flight_stats(request, equipment_qs)

    if request.method == "POST":
        form = EquipmentForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)

            # ✅ User scoping on create
            obj.user = request.user

            if not obj.placed_in_service_date and obj.purchase_date:
                obj.placed_in_service_date = obj.purchase_date

            if obj.business_use_percent is None:
                obj.business_use_percent = Decimal("100.00")

            obj.save()
            form.save_m2m()
            messages.success(request, "Equipment added.")
            return redirect("equipment:equipment_list")

        messages.error(request, "There was a problem saving the equipment.")

    else:
        form = EquipmentForm(user=request.user)

    return render(
        request,
        "equipment/equipment_list.html",
        {"form": form, "equipment": equipment, "current_page": "equipment"},
    )


# -------------------------------------------------------------------
# Equipment edit / delete
# -------------------------------------------------------------------
@login_required
def equipment_create(request):
    """
    Dedicated create view (if you use it elsewhere).
    """
    if request.method == "POST":
        form = EquipmentForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user

            if not obj.placed_in_service_date and obj.purchase_date:
                obj.placed_in_service_date = obj.purchase_date

            if obj.business_use_percent is None:
                obj.business_use_percent = Decimal("100.00")

            obj.save()
            form.save_m2m()
            messages.success(request, "Equipment added.")
            return redirect("equipment:equipment_list")

        messages.error(request, "There was a problem saving the equipment.")
    else:
        form = EquipmentForm(user=request.user)

    return render(
        request,
        "equipment/equipment_form.html",
        {"form": form, "current_page": "equipment"},
    )


@login_required
def equipment_edit(request, pk):
    item = get_object_or_404(Equipment, user=request.user, pk=pk)

    if request.method == "POST":
        form = EquipmentForm(request.POST, request.FILES, instance=item, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)

            # ✅ Ensure user stays correct even if tampered POST
            obj.user = request.user

            if not obj.placed_in_service_date and obj.purchase_date:
                obj.placed_in_service_date = obj.purchase_date

            if obj.business_use_percent is None:
                obj.business_use_percent = Decimal("100.00")

            obj.save()
            form.save_m2m()
            messages.success(request, "Equipment updated.")
            return redirect("equipment:equipment_list")

        messages.error(request, "There was a problem updating the equipment.")
    else:
        form = EquipmentForm(instance=item, user=request.user)

    return render(
        request,
        "equipment/equipment_edit.html",
        {"form": form, "item": item, "current_page": "equipment"},
    )


@login_required
def equipment_delete(request, pk):
    item = get_object_or_404(Equipment, user=request.user, pk=pk)

    if request.method == "POST":
        name = str(item)
        item.delete()
        messages.success(request, f'Equipment "{name}" deleted.')
        return redirect("equipment:equipment_list")

    return render(
        request,
        "equipment/equipment_confirm_delete.html",
        {"equipment": item, "current_page": "equipment"},
    )


# -------------------------------------------------------------------
# PDF export (requires WeasyPrint)
# -------------------------------------------------------------------
@login_required
def equipment_pdf(request):
    """
    PDF of the user's inventory (requires WeasyPrint).
    """
    if not WEASYPRINT_AVAILABLE:
        messages.error(request, "PDF generation is not available (WeasyPrint not installed).")
        return redirect("equipment:equipment_list")

    equipment_qs = _equipment_queryset(request.user)
    equipment = _attach_drone_flight_stats(request, equipment_qs)

    template = get_template("equipment/equipment_pdf.html")
    html_string = template.render(
        {"equipment": equipment, "static_logo": static("images/airborne_logo.png")}
    )

    with tempfile.NamedTemporaryFile(suffix=".pdf") as output:
        HTML(string=html_string).write_pdf(
            output.name,
            stylesheets=[CSS(string="@page { size: Letter; margin: 0.5in; }")],
        )
        output.seek(0)
        response = HttpResponse(output.read(), content_type="application/pdf")

    response["Content-Disposition"] = 'inline; filename="equipment.pdf"'
    return response


@login_required
def equipment_pdf_single(request, pk):
    """
    PDF for one equipment item (requires WeasyPrint).
    """
    if not WEASYPRINT_AVAILABLE:
        messages.error(request, "PDF generation is not available (WeasyPrint not installed).")
        return redirect("equipment:equipment_list")

    item = get_object_or_404(Equipment, user=request.user, pk=pk)

    template = get_template("equipment/equipment_pdf_single.html")
    html_string = template.render(
        {"item": item, "static_logo": static("images/airborne_logo.png")}
    )

    filename = f"equipment_{_safe_filename(item.name)}.pdf"

    with tempfile.NamedTemporaryFile(suffix=".pdf") as output:
        HTML(string=html_string).write_pdf(
            output.name,
            stylesheets=[CSS(string="@page { size: Letter; margin: 0.5in; }")],
        )
        output.seek(0)
        response = HttpResponse(output.read(), content_type="application/pdf")

    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


# -------------------------------------------------------------------
# CSV export
# -------------------------------------------------------------------
@login_required
def export_equipment_csv(request):
    equipment_qs = _equipment_queryset(request.user)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="equipment.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Name",
            "Type",
            "Brand",
            "Model",
            "Serial Number",
            "FAA Number",
            "FAA Certificate URL",
            "Purchase Date",
            "Placed In Service",
            "Purchase Cost",
            "Receipt URL",
            "Property Type",
            "Depreciation Method",
            "Useful Life (years)",
            "Business Use (%)",
            "Date Sold",
            "Sale Price",
            "Active",
            "Notes",
        ]
    )

    for e in equipment_qs:
        writer.writerow(
            [
                e.name,
                e.get_equipment_type_display()
                if hasattr(e, "get_equipment_type_display")
                else (e.equipment_type or ""),
                e.brand or "",
                e.model or "",
                e.serial_number or "",
                e.faa_number or "",
                e.faa_certificate.url if e.faa_certificate else "",
                e.purchase_date or "",
                getattr(e, "placed_in_service_date", None) or "",
                e.purchase_cost or "",
                e.receipt.url if e.receipt else "",
                getattr(e, "property_type", "") or "",
                getattr(e, "depreciation_method", "") or "",
                getattr(e, "useful_life_years", "") or "",
                getattr(e, "business_use_percent", "") or "",
                getattr(e, "date_sold", "") or "",
                getattr(e, "sale_price", "") or "",
                "Yes" if e.active else "No",
                (e.notes or "").replace("\n", " ").replace("\r", " "),
            ]
        )

    return response


# -------------------------------------------------------------------
# Drone safety profile suggestion endpoint (global catalog)
# -------------------------------------------------------------------
@login_required
@require_GET
def drone_profile_suggest(request: HttpRequest) -> JsonResponse:
    name = (request.GET.get("name") or "").strip()
    brand = (request.GET.get("brand") or "").strip() or None

    if not name:
        return JsonResponse({"found": False})

    profile = find_best_drone_profile(brand, name)
    if not profile:
        return JsonResponse({"found": False})

    return JsonResponse(
        {"found": True, "id": str(profile.pk), "full_display_name": profile.full_display_name}
    )


# -------------------------------
# Drone Safety Profile CRUD (global)
# -------------------------------
@login_required
def drone_safety_profile_list(request):
    sort = request.GET.get("sort", "brand")
    direction = request.GET.get("dir", "asc")

    sort_map = {
        "brand": "brand",
        "model": "model_name",
        "display": "full_display_name",
        "year": "year_released",
        "active": "active",
    }
    sort_key = sort_map.get(sort, "brand")
    order_by = f"-{sort_key}" if direction == "desc" else sort_key
    direction = "desc" if direction == "desc" else "asc"
    profiles = DroneSafetyProfile.objects.all().order_by(order_by)
    return render(
        request,
        "equipment/drone_safety_profile_list.html",
        {"profiles": profiles, "sort": sort, "dir": direction},
    )


@staff_member_required
def drone_safety_profile_create(request):
    if request.method == "POST":
        form = DroneSafetyProfileForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Drone safety profile created.")
            return redirect("equipment:drone_safety_profile_list")
        messages.error(request, "There was a problem saving the profile.")
    else:
        form = DroneSafetyProfileForm()

    return render(
        request,
        "equipment/drone_safety_profile_form.html",
        {"form": form, "title": "Create Drone Safety Profile"},
    )


@staff_member_required
def drone_safety_profile_edit(request, pk):
    profile = get_object_or_404(DroneSafetyProfile, pk=pk)

    if request.method == "POST":
        form = DroneSafetyProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Drone safety profile updated.")
            return redirect("equipment:drone_safety_profile_list")
        messages.error(request, "There was a problem updating the profile.")
    else:
        form = DroneSafetyProfileForm(instance=profile)

    return render(
        request,
        "equipment/drone_safety_profile_form.html",
        {"form": form, "title": f"Edit {profile.full_display_name}", "profile": profile},
    )


@staff_member_required
def drone_safety_profile_delete(request, pk):
    profile = get_object_or_404(DroneSafetyProfile, pk=pk)

    if request.method == "POST":
        name = profile.full_display_name or f"{profile.brand} {profile.model_name}"
        profile.delete()
        messages.success(request, f"Deleted drone safety profile: {name}.")
        return redirect("equipment:drone_safety_profile_list")

    return render(
        request,
        "equipment/drone_safety_profile_confirm_delete.html",
        {"profile": profile},
    )
