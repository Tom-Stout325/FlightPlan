import csv
import tempfile
from decimal import Decimal

from django.contrib import messages
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
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _equipment_queryset():
    """
    Central place to define inventory ordering.
    """
    return Equipment.objects.all().order_by("-active", "-purchase_date", "equipment_type", "name")


def _attach_drone_flight_stats(equipment_qs):
    """
    Adds:
      - flights_count
      - total_duration
    for drone items that have serial_number.
    """
    drone_serials = list(
        equipment_qs.filter(equipment_type="Drone")
        .exclude(serial_number__isnull=True)
        .exclude(serial_number__exact="")
        .values_list("serial_number", flat=True)
    )

    stats_map = {}
    if drone_serials:
        stats = (
            FlightLog.objects
            .filter(drone_serial__in=drone_serials)
            .values("drone_serial")
            .annotate(
                flights_count=Count("id"),
                total_duration=Sum("air_time"),
            )
        )
        stats_map = {row["drone_serial"]: row for row in stats}

    equipment = []
    for e in equipment_qs:
        if e.equipment_type == "Drone" and e.serial_number:
            row = stats_map.get(e.serial_number, {})
            e.flights_count = row.get("flights_count", 0)
            e.total_duration = row.get("total_duration")
        else:
            e.flights_count = 0
            e.total_duration = None
        equipment.append(e)

    return equipment


def _safe_filename(name: str) -> str:
    return "".join(ch for ch in (name or "") if ch.isalnum() or ch in (" ", "-", "_")).strip().replace(" ", "_") or "equipment"


# -------------------------------------------------------------------
# Views
# -------------------------------------------------------------------
@login_required
def equipment_list(request):
    """
    Inventory list + inline create form.
    """
    equipment_qs = _equipment_queryset()
    equipment = _attach_drone_flight_stats(equipment_qs)

    if request.method == "POST":
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)

            # Convenience: if placed-in-service is blank and purchase_date exists, set it
            if not obj.placed_in_service_date and obj.purchase_date:
                obj.placed_in_service_date = obj.purchase_date

            # Convenience: default business_use_percent to 100 for typical business equipment
            if obj.business_use_percent is None:
                obj.business_use_percent = Decimal("100.00")

            obj.save()
            form.save_m2m()
            messages.success(request, "Equipment added.")
            return redirect("equipment:equipment_list")

        messages.error(request, "There was a problem saving the equipment.")
    else:
        form = EquipmentForm()

    return render(
        request,
        "equipment/equipment_list.html",
        {
            "equipment": equipment,
            "form": form,
            "current_page": "equipment",
            "weasyprint_available": WEASYPRINT_AVAILABLE,
        },
    )


@login_required
def equipment_create(request):
    """
    Dedicated create endpoint (kept for backward compatibility).
    If you only use inline create on the list page, you can remove this route later.
    """
    if request.method != "POST":
        return redirect("equipment:equipment_list")

    form = EquipmentForm(request.POST, request.FILES)
    if form.is_valid():
        obj = form.save(commit=False)

        if not obj.placed_in_service_date and obj.purchase_date:
            obj.placed_in_service_date = obj.purchase_date

        if obj.business_use_percent is None:
            obj.business_use_percent = Decimal("100.00")

        obj.save()
        form.save_m2m()
        messages.success(request, "Equipment added.")
        return redirect("equipment:equipment_list")

    messages.error(request, "There was a problem saving the equipment.")

    # Re-render list page with errors
    equipment_qs = _equipment_queryset()
    equipment = _attach_drone_flight_stats(equipment_qs)
    return render(
        request,
        "equipment/equipment_list.html",
        {"form": form, "equipment": equipment, "current_page": "equipment"},
    )


@login_required
def equipment_edit(request, pk):
    item = get_object_or_404(Equipment, pk=pk)

    if request.method == "POST":
        form = EquipmentForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            obj = form.save(commit=False)

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
        form = EquipmentForm(instance=item)

    return render(
        request,
        "equipment/equipment_edit.html",
        {"form": form, "item": item, "current_page": "equipment"},
    )


@login_required
def equipment_delete(request, pk):
    item = get_object_or_404(Equipment, pk=pk)

    if request.method == "POST":
        name = item.name
        item.delete()
        messages.success(request, f'Equipment "{name}" deleted.')
        return redirect("equipment:equipment_list")

    return render(
        request,
        "equipment/equipment_confirm_delete.html",
        {"equipment": item, "current_page": "equipment"},
    )


@login_required
def equipment_pdf(request):
    """
    PDF of the full inventory (requires WeasyPrint).
    """
    if not WEASYPRINT_AVAILABLE:
        messages.error(request, "PDF export is not available on this system.")
        return redirect("equipment:equipment_list")

    equipment = Equipment.objects.all().order_by("equipment_type", "name")
    logo_url = request.build_absolute_uri(static("images/logo.png"))

    context = {
        "equipment": equipment,
        "logo_url": logo_url,
    }

    template = get_template("equipment/equipment_pdf.html")
    html_string = template.render(context, request=request)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="equipment_inventory.pdf"'

    with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(target=tmp_file.name)
        tmp_file.seek(0)
        response.write(tmp_file.read())

    return response


@login_required
def equipment_pdf_single(request, pk):
    """
    PDF for a single piece of equipment (requires WeasyPrint).
    """
    if not WEASYPRINT_AVAILABLE:
        messages.error(request, "PDF export is not available on this system.")
        return redirect("equipment:equipment_list")

    item = get_object_or_404(Equipment, pk=pk)
    logo_url = request.build_absolute_uri(static("images/logo.png"))

    faa_is_pdf = bool(item.faa_certificate and item.faa_certificate.name.lower().endswith(".pdf"))
    receipt_is_pdf = bool(item.receipt and item.receipt.name.lower().endswith(".pdf"))

    context = {
        "item": item,
        "logo_url": logo_url,
        "faa_is_pdf": faa_is_pdf,
        "receipt_is_pdf": receipt_is_pdf,
    }

    template = get_template("equipment/equipment_pdf_single.html")
    html_string = template.render(context, request=request)

    safe = _safe_filename(item.name)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{safe}_equipment.pdf"'

    with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(target=tmp_file.name)
        tmp_file.seek(0)
        response.write(tmp_file.read())

    return response


@login_required
def export_equipment_csv(request):
    """
    CSV export with the new tax/depreciation fields included.
    """
    equipment = Equipment.objects.all().order_by("equipment_type", "name")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="equipment.csv"'
    writer = csv.writer(response)

    writer.writerow([
        "Name",
        "Type",
        "Brand",
        "Model",
        "Serial Number",
        "FAA Number",
        "FAA Certificate URL",
        "Purchase Date",
        "Placed In Service Date",
        "Purchase Cost",
        "Receipt URL",
        "Property Type",
        "Depreciation Method",
        "Useful Life Years",
        "Business Use Percent",
        "Date Sold",
        "Sale Price",
        "Deducted Full Cost",
        "Active",
        "Notes",
    ])

    for e in equipment:
        writer.writerow([
            e.name,
            e.get_equipment_type_display() if hasattr(e, "get_equipment_type_display") else (e.equipment_type or ""),
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
            e.date_sold or "",
            e.sale_price or "",
            "Yes" if e.deducted_full_cost else "No",
            "Yes" if e.active else "No",
            (e.notes or "").replace("\n", " ").replace("\r", " "),
        ])

    return response


# -------------------------------------------------------------------
# Optional: Drone safety profile suggestion endpoint (if you use it)
# -------------------------------------------------------------------
@login_required
@require_GET
def drone_profile_suggest(request: HttpRequest) -> JsonResponse:
    """
    GET params:
      - brand (optional)
      - name
    Returns:
      {found: bool, id, full_display_name}
    """
    name = (request.GET.get("name") or "").strip()
    brand = (request.GET.get("brand") or "").strip() or None

    if not name:
        return JsonResponse({"found": False})

    profile = find_best_drone_profile(brand, name)
    if not profile:
        return JsonResponse({"found": False})

    return JsonResponse(
        {
            "found": True,
            "id": str(profile.pk),
            "full_display_name": profile.full_display_name,
        }
    )


    
# -------------------------------
# Drone Safety Profile CRUD
# -------------------------------

@login_required
def drone_safety_profile_list(request):
    sort = request.GET.get("sort", "brand")
    direction = request.GET.get("dir", "asc")

    # Map friendly sort keys → model fields
    sort_map = {
        "brand": "brand",
        "model": "model_name",
        "display": "full_display_name",
        "year": "year_released",
        "active": "active",
    }

    sort_key = sort_map.get(sort, "brand")

    if direction == "desc":
        order_by = f"-{sort_key}"
    else:
        order_by = sort_key
        direction = "asc"  # normalize anything else

    profiles = DroneSafetyProfile.objects.all().order_by(order_by)

    context = {
        "profiles": profiles,
        "sort": sort,
        "dir": direction,
    }
    return render(
        request,
        "equipment/drone_safety_profile_list.html",
        context,
    )



@login_required
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
        {
            "form": form,
            "title": "Add Drone Safety Profile",
        },
    )


@login_required
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
        {
            "form": form,
            "title": f"Edit {profile.full_display_name}",
            "profile": profile,
        },
    )


@login_required
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
        {
            "profile": profile,
        },
    )




