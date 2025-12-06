import csv
import tempfile
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.templatetags.static import static 
from django.db.models import Count, Sum
import json
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET
from .utils import find_best_drone_profile

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False

from .models import *
from flightlogs.models import FlightLog
from .forms import *


@login_required
def equipment_list(request):
    equipment_qs = Equipment.objects.all().order_by('-active', '-purchase_date', 'name')

    drone_serials = [
        e.serial_number for e in equipment_qs
        if e.equipment_type == 'Drone' and e.serial_number
    ]

    stats = (
        FlightLog.objects
        .filter(drone_serial__in=drone_serials)
        .values('drone_serial')
        .annotate(
            flights_count=Count('id'),
            total_duration=Sum('air_time')  
        )
    )
    stats_map = {row['drone_serial']: row for row in stats}

    equipment = []
    for e in equipment_qs:
        if e.equipment_type == 'Drone' and e.serial_number:
            s = stats_map.get(e.serial_number, {})
            e.flights_count = s.get('flights_count', 0)
            e.total_duration = s.get('total_duration')
        else:
            e.flights_count = 0
            e.total_duration = None
        equipment.append(e)

    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment added.')
            return redirect('equipment:equipment_list')
        messages.error(request, 'There was a problem saving the equipment.')
    else:
        form = EquipmentForm()

    return render(
        request,
        'equipment/equipment_list.html',
        {'equipment': equipment, 'form': form, 'current_page': 'equipment'}
    )


@login_required
def equipment_create(request):
    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment added.')
            return redirect('equipment:equipment_list')
        # Log form errors for debugging
        print("POST data:", request.POST)
        print("FILES data:", request.FILES)
        print("Form errors:", form.errors)
        messages.error(request, 'There was a problem saving the equipment.')
    else:
        form = EquipmentForm()

    return render(
        request,
        'equipment/equipment_list.html',
        {'form': form, 'equipment': Equipment.objects.all(), 'current_page': 'equipment'}
    )


@login_required
def equipment_edit(request, pk):
    item = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment updated.')
            return redirect('equipment:equipment_list')
        messages.error(request, 'There was a problem updating the equipment.')
    else:
        form = EquipmentForm(instance=item)

    return render(request, 'equipment/equipment_edit.html', {'form': form, 'item': item, 'current_page': 'equipment'})


@login_required
def equipment_delete(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        name = equipment.name
        equipment.delete()
        messages.success(request, f'Equipment "{name}" deleted.')
        return redirect('equipment:equipment_list')
    return render(request, 'equipment/equipment_confirm_delete.html', {'equipment': equipment, 'current_page': 'equipment'})


@login_required
def equipment_pdf(request):
    equipment = Equipment.objects.all().order_by('equipment_type', 'name')
    logo_url = request.build_absolute_uri(static('images/logo.png'))
    context = {'equipment': equipment, 'logo_url': logo_url}

    template = get_template('equipment/equipment_pdf.html')
    html_string = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename=equipment_inventory.pdf'

    with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(target=tmp_file.name)
        tmp_file.seek(0)
        response.write(tmp_file.read())

    return response


@login_required
def equipment_pdf_single(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    logo_url = request.build_absolute_uri(static('images/logo.png'))

    faa_is_pdf = equipment.faa_certificate.name.lower().endswith('.pdf') if equipment.faa_certificate else False
    receipt_is_pdf = equipment.receipt.name.lower().endswith('.pdf') if equipment.receipt else False

    context = {
        'item': equipment,
        'logo_url': logo_url,
        'faa_is_pdf': faa_is_pdf,
        'receipt_is_pdf': receipt_is_pdf,
    }

    template = get_template('equipment/equipment_pdf_single.html')
    html_string = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename={equipment.name}_equipment.pdf'

    with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(target=tmp_file.name)
        tmp_file.seek(0)
        response.write(tmp_file.read())

    return response


@login_required
def export_equipment_csv(request):
    equipment = Equipment.objects.all()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="equipment.csv"'
    writer = csv.writer(response)

    writer.writerow([
        'Name', 'Type', 'Brand', 'Model', 'Serial Number', 'FAA Number',
        'FAA Certificate URL', 'Purchase Date', 'Purchase Cost', 'Receipt URL',
        'Date Sold', 'Sale Price', 'Deducted Full Cost', 'Active', 'Notes',
    ])

    for e in equipment:
        writer.writerow([
            e.name,
            e.get_equipment_type_display(),
            e.brand,
            e.model,
            e.serial_number,
            e.faa_number,
            e.faa_certificate.url if e.faa_certificate else '',
            e.purchase_date,
            e.purchase_cost,
            e.receipt.url if e.receipt else '',
            e.date_sold,
            e.sale_price,
            'Yes' if e.deducted_full_cost else 'No',
            'Yes' if e.active else 'No',
            (e.notes or '').replace('\n', ' ').replace('\r', ''),
        ])

    return response




@login_required
@require_GET
def drone_profile_suggest_view(request: HttpRequest) -> JsonResponse:
    """
    GET /equipment/api/drone-suggest/?brand=DJI&name=Mavic+4+Pro

    Returns a simple JSON suggestion, or {"found": false} if nothing.
    """
    brand = request.GET.get("brand") or ""
    name = request.GET.get("name") or ""

    profile = find_best_drone_profile(brand, name)

    if not profile:
        return JsonResponse({"found": False})

    return JsonResponse(
        {
            "found": True,
            "id": profile.id,
            "full_display_name": profile.full_display_name,
            "brand": profile.brand,
            "safety_features": profile.safety_features,
        }
    )