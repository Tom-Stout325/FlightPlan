# airspace/views.py
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Q
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, TemplateView
from formtools.wizard.views import SessionWizardView
from django.template.loader import render_to_string
from dal import autocomplete

from .utils import dms_to_decimal, generate_short_description
from .utils import decimal_to_dms  

from equipment.models import Equipment
from flightlogs.models import FlightLog
from pilot.models import PilotProfile
from .constants.conops import CONOPS_SECTIONS

logger = logging.getLogger(__name__)

from .forms import TIMEFRAME_CHOICES

from .forms import (
    WaiverApplicationDescriptionForm, 
    WaiverPlanningForm
)

from .models import (
        ConopsSection, 
        WaiverApplication, 
        WaiverPlanning, 
        Airport
)
from .services import (
    ensure_conops_sections,
    generate_conops_section_text,
    generate_waiver_description_text,
    validate_conops_section,
    planning_aircraft_summary,
)


from weasyprint import HTML









class WaiverEquipmentChecklistView(LoginRequiredMixin, TemplateView):
    """
    Standalone printable checklist of required on-site equipment
    for waiver / ops planning. Does not store data – purely a guide.
    """
    template_name = "airspace/waiver_equipment_checklist.html"






class AirspacePortalView(LoginRequiredMixin, TemplateView):
    template_name = "airspace/airspace_portal.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # ---- Flight stats ----
        full_name = f"{user.first_name} {user.last_name}".strip()
        flights = FlightLog.objects.filter(pilot_in_command__iexact=full_name)

        ctx["total_flights"] = flights.count()

        # Sum the air_time DurationField safely
        total_flight_time = flights.aggregate(total=Sum("air_time"))["total"]
        ctx["total_flight_time"] = total_flight_time  # can be None if no flights

        # ---- Equipment stats ----
        ctx["active_drones"] = Equipment.objects.filter(
            equipment_type="Drone",
            active=True,
        ).count()

        # ---- Waiver stats (placeholder for now) ----
        ctx["total_waivers"] = 0
        ctx["waivers_with_conops"] = 0
        ctx["upcoming_waivers"] = 0

        return ctx





@login_required
def airspace_helper(request):
    return render(request, "airspace/airspace_guide.html")





@login_required
def waiver_planning_new(request):
    """
    Step 1 – Create or edit a WaiverPlanning entry.
    """
    planning_id = request.GET.get("planning_id")
    planning = None

    if planning_id:
        planning = get_object_or_404(WaiverPlanning, id=planning_id, user=request.user)

    if request.method == "POST":
        form = WaiverPlanningForm(request.POST, user=request.user, instance=planning)
        if form.is_valid():
            planning_obj = form.save(commit=False)
            planning_obj.user = request.user
            planning_obj.save()
            form.save_m2m()

            return redirect(
                "airspace:waiver_application_overview",
                planning_id=planning_obj.id,
            )
    else:
        form = WaiverPlanningForm(user=request.user, instance=planning)

    # ----------------------------------------
    # Pilot profile data for JS auto-fill
    # ----------------------------------------
    pilot_profile_data = []
    pilot_field = form.fields.get("pilot_profile")
    pilot_qs = pilot_field.queryset if pilot_field is not None else PilotProfile.objects.none()

    for profile in pilot_qs.select_related("user"):
        total_seconds = 0
        try:
            total_seconds = profile.flight_time_total() or 0
        except Exception:
            total_seconds = 0

        flight_hours = round(total_seconds / 3600, 1) if total_seconds else 0

        pilot_profile_data.append(
            {
                "id": profile.id,
                "license_number": profile.license_number or "",
                "flight_hours": flight_hours,
            }
        )

    # ----------------------------------------
    # Drone safety data for JS auto-fill
    # ----------------------------------------
    drone_safety_data = []
    aircraft_field = form.fields.get("aircraft")

    if aircraft_field is not None:
        equipment_qs = aircraft_field.queryset.select_related("drone_safety_profile")
        for equip in equipment_qs:
            profile = getattr(equip, "drone_safety_profile", None)
            drone_safety_data.append(
                {
                    "id": equip.id,  
                    "safety_features": (profile.safety_features if profile else "") or "",
                }
            )

    context = {
        "form": form,
        "planning": planning,
        "planning_mode": "edit" if planning else "new",
        "pilot_profile_data": pilot_profile_data,
        "drone_safety_data": drone_safety_data,
    }
    return render(request, "airspace/waiver_planning_form.html", context)





class WaiverPlanningDescriptionForm(WaiverPlanningForm):
    """
    Slimmed-down version of WaiverPlanningForm used on the Description page.
    Keeps the same widget/__init__ behavior, but only exposes fields that
    influence the Description of Ops prompt and narrative.
    """

    class Meta(WaiverPlanningForm.Meta):
        fields = [
            # Aircraft / pilot
            "aircraft",
            "aircraft_manual",
            "pilot_profile",
            "pilot_flight_hours",

            # Waivers
            "operates_under_10739",
            "oop_waiver_document",
            "oop_waiver_number",
            "operates_under_107145",
            "mv_waiver_document",
            "mv_waiver_number",

            # Purpose of operations
            "purpose_operations",
            "purpose_operations_details",

            # Location / venue
            "venue_name",
            "street_address",
            "location_city",
            "location_state",
            "zip_code",
            "launch_location",

            # Safety / insurance
            "uses_drone_detection",
            "uses_flight_tracking",
            "has_visual_observer",
            "insurance_provider",
            "insurance_coverage_limit",
            "safety_features_notes",

            # Operational profile
            "aircraft_count",
            "flight_duration",
            "flights_per_day",
            "ground_environment",
            "estimated_crowd_size",
            "prepared_procedures",
        ]





@login_required
def waiver_application_overview(request, planning_id):
    """
    Step 1.5 – Overview of the FAA waiver application, populated from WaiverPlanning.
    Ensures a WaiverApplication exists for this planning entry.
    """
    planning = get_object_or_404(WaiverPlanning, id=planning_id, user=request.user)

    application, _ = WaiverApplication.objects.get_or_create(
        planning=planning,
        user=request.user,
    )

    # ----- Build timeframe label list from stored codes -----
    timeframe_labels = []
    if planning.timeframe:
        code_to_label = dict(TIMEFRAME_CHOICES)  
        timeframe_labels = [code_to_label.get(code, code) for code in planning.timeframe]

    lat_dms = decimal_to_dms(planning.location_latitude, is_lat=True) if planning.location_latitude else None
    lon_dms = decimal_to_dms(planning.location_longitude, is_lat=False) if planning.location_longitude else None

    if request.method == "POST":
        if "back" in request.POST:
            return redirect("airspace:waiver_planning_list")
        if "continue" in request.POST:
            return redirect("airspace:waiver_application_description", pk=application.pk)

    context = {
        "planning": planning,
        "application": application,
        "timeframe_labels": timeframe_labels,
        "lat_dms": lat_dms,
        "lon_dms": lon_dms,
    }
    return render(request, "airspace/waiver_application_overview.html", context)




@login_required
def waiver_application_description(request, pk):
    """
    Step 2 – Edit the planning inputs that drive the Description of Ops,
    generate text (unless locked), and save manual edits.
    """
    application = get_object_or_404(WaiverApplication, pk=pk, user=request.user)
    planning = application.planning

    if request.method == "POST":
        planning_form = WaiverPlanningDescriptionForm(
            request.POST,
            instance=planning,
            user=request.user,
        )

        application.locked_description = ("locked_description" in request.POST)
        application.save(update_fields=["locked_description"])

        # -------------------------
        # Generate (overwrite)
        # -------------------------
        if "generate" in request.POST:
            if application.locked_description:
                messages.error(request, "Description is locked. Unlock it to regenerate.")
                return redirect("airspace:waiver_application_description", pk=application.pk)

            if not planning_form.is_valid():
                messages.error(request, "Please fix the errors above before generating.")
                return redirect("airspace:waiver_application_description", pk=application.pk)

            planning_form.save()

            try:
                model = getattr(settings, "OPENAI_TEXT_MODEL", "gpt-4.1-mini")
                text = generate_waiver_description_text(planning, model=model)

                if not (text or "").strip():
                    raise RuntimeError("Generated description was empty.")

                application.description = text
                application.save(update_fields=["description"])

                planning.generated_description_at = timezone.now()
                planning.save(update_fields=["generated_description_at"])

                messages.success(request, "Description of Operations generated.")
            except Exception as exc:
                messages.error(request, f"Could not generate Description of Operations: {exc}")

            return redirect("airspace:waiver_application_description", pk=application.pk)

        # -------------------------
        # Save Changes (keep edits)
        # -------------------------
        app_form = WaiverApplicationDescriptionForm(request.POST, instance=application)

        if planning_form.is_valid() and app_form.is_valid():
            planning_form.save()
            app_form.save()
            messages.success(request, "Changes saved.")
            return redirect("airspace:waiver_application_description", pk=application.pk)

        messages.error(request, "Please fix the errors below and try again.")

    planning_form = WaiverPlanningDescriptionForm(instance=planning, user=request.user)
    app_form = WaiverApplicationDescriptionForm(instance=application)
    aircraft_ctx = planning_aircraft_summary(planning)

    return render(
        request,
        "airspace/waiver_application_description.html",
        {
            "planning": planning,
            "application": application,
            "planning_form": planning_form,
            "app_form": app_form,
            "aircraft_ctx": aircraft_ctx,
        },
    )





class WaiverPlanningListView(LoginRequiredMixin, ListView):
    """
    Lists all WaiverPlanning entries for the logged-in user.
    """
    model = WaiverPlanning
    template_name = "airspace/waiver_planning_list.html"
    context_object_name = "planning_list"
    paginate_by = 20

    def get_queryset(self):
        return (
            WaiverPlanning.objects.filter(user=self.request.user).order_by("-created_at")
        )





@login_required
def waiver_planning_delete(request, pk):
    """
    Delete a WaiverPlanning entry (user-restricted).
    """
    planning = get_object_or_404(
        WaiverPlanning,
        pk=pk,
        user=request.user,
    )

    if request.method == "POST":
        planning.delete()
        messages.success(request, "Waiver planning entry deleted.")
        return redirect("airspace:waiver_planning_list")

    return render(
        request,
        "airspace/waiver_planning_confirm_delete.html",
        {"planning": planning},
    )





@login_required
def conops_overview(request, pk):
    """
    CONOPS entry point for a waiver application.
    Shows all CONOPS sections and their status.
    """
    application = get_object_or_404(
        WaiverApplication,
        pk=pk,
        user=request.user,
    )

    ensure_conops_sections(application)
    sections = application.conops_sections.order_by("id")

    return render(
        request,
        "airspace/conops_overview.html",
        {
            "application": application,
            "planning": application.planning,
            "sections": sections,
        },
    )


@login_required
def conops_section_edit(request, pk, section_key):
    application = get_object_or_404(
        WaiverApplication,
        pk=pk,
        user=request.user,
    )

    section = get_object_or_404(
        ConopsSection,
        application=application,
        section_key=section_key,
    )

    if request.method == "POST":
        # Persist lock toggle on every POST
        section.locked = ("locked" in request.POST)
        section.save(update_fields=["locked"])

        # -------------------------
        # Generate section text
        # -------------------------
        if "generate" in request.POST:
            if section.locked:
                messages.error(request, "This section is locked. Unlock it to regenerate.")
                return redirect(
                    "airspace:conops_section_edit",
                    pk=application.pk,
                    section_key=section.section_key,
                )

            try:
                model = getattr(settings, "OPENAI_TEXT_MODEL", "gpt-4.1-mini")
                text = generate_conops_section_text(
                    application=application,
                    section=section,
                    model=model,
                )

                if not (text or "").strip():
                    raise RuntimeError("Generated section text was empty.")

                section.content = text
                section.generated_at = timezone.now()
                section.save(update_fields=["content", "generated_at"])

                validate_conops_section(section)

                messages.success(request, f"{section.title} generated.")
            except Exception as exc:
                messages.error(request, f"Could not generate section: {exc}")

            return redirect(
                "airspace:conops_section_edit",
                pk=application.pk,
                section_key=section.section_key,
            )

        # -------------------------
        # Save manual edits
        # -------------------------
        if "save" in request.POST:
            section.content = request.POST.get("content", "")
            section.save(update_fields=["content"])

            validate_conops_section(section)

            messages.success(request, "Section saved.")
            return redirect(
                "airspace:conops_section_edit",
                pk=application.pk,
                section_key=section.section_key,
            )

    return render(
        request,
        "airspace/conops_section_edit.html",
        {
            "application": application,
            "section": section,
        },
    )





@login_required
def conops_review(request, application_id):
    """
    Mobile-first accordion editor for CONOPS sections.

    - Progress bar context (complete/total/percent + locked count + word count)
    - Lock All / Unlock All actions
    - Save: persists edits + lock states and updates validation flags
    - Regenerate: regenerates ONLY unlocked sections
    """
    application = get_object_or_404(
        WaiverApplication,
        pk=application_id,
        user=request.user,
    )

    ensure_conops_sections(application)

    AUTO_ONLY = {"cover_page", "compliance_statement", "appendices"}

    # Pull all sections once
    sections_qs = application.conops_sections.all()
    sections_by_key = {s.section_key: s for s in sections_qs}

    def _normalize_validation(section_obj):
        """
        Normalizes validate_conops_section to:
          (ok: bool, missing: list[str], fix_url_name: str|None)
        """
        res = validate_conops_section(section_obj)

        if isinstance(res, dict):
            return bool(res.get("ok")), list(res.get("missing") or []), res.get("fix_url")

        if isinstance(res, (list, tuple)) and len(res) >= 2:
            ok = bool(res[0])
            missing = list(res[1] or [])
            fix_url_name = res[2] if len(res) >= 3 else None
            return ok, missing, fix_url_name

        return bool(getattr(section_obj, "is_complete", True)), [], None

    # -------------------------
    # POST actions
    # -------------------------
    if request.method == "POST":
        action = request.POST.get("action", "save")

        # --- Lock All / Unlock All ---
        if action in ("lock_all", "unlock_all"):
            lock_value = (action == "lock_all")

            for sec in sections_by_key.values():
                if sec.locked != lock_value:
                    sec.locked = lock_value
                    sec.save(update_fields=["locked"])

            messages.success(
                request,
                "All sections locked." if lock_value else "All sections unlocked.",
            )
            return redirect("airspace:conops_review", application_id=application.id)

        # --- Regenerate unlocked sections ---
        if action == "regenerate":
            regenerated = 0

            for section_key, _title in CONOPS_SECTIONS:
                sec = sections_by_key.get(section_key)
                if not sec:
                    continue

                # Persist lock toggle first
                new_locked = bool(request.POST.get(f"locked_{section_key}"))
                if sec.locked != new_locked:
                    sec.locked = new_locked
                    sec.save(update_fields=["locked"])

                if sec.locked:
                    continue

                try:
                    model = getattr(settings, "OPENAI_TEXT_MODEL", "gpt-4.1-mini")
                    generate_conops_section_text(
                        application=application,
                        section=sec,
                        model=model,
                    )
                    regenerated += 1
                except Exception as exc:
                    messages.error(request, f"Could not regenerate {sec.title}: {exc}")

            messages.success(
                request,
                f"Regenerated {regenerated} unlocked section(s). Locked sections were preserved.",
            )
            return redirect("airspace:conops_review", application_id=application.id)

        # --- Default: Save edits (no regeneration) ---
        saved = 0

        for section_key, _title in CONOPS_SECTIONS:
            sec = sections_by_key.get(section_key)
            if not sec:
                continue

            # Lock toggle
            new_locked = bool(request.POST.get(f"locked_{section_key}"))
            changed_fields = []
            if sec.locked != new_locked:
                sec.locked = new_locked
                changed_fields.append("locked")

            # Editable text for non-auto sections
            if section_key not in AUTO_ONLY:
                posted_text = request.POST.get(f"content_{section_key}", "") or ""
                if posted_text != (sec.content or ""):
                    sec.content = posted_text
                    changed_fields.append("content")

            if changed_fields:
                sec.save(update_fields=changed_fields)

            # Validate completeness flag (this function also saves is_complete/validated_at)
            _normalize_validation(sec)
            saved += 1

        messages.success(request, f"Saved {saved} section(s).")
        return redirect("airspace:conops_review", application_id=application.id)

    # -------------------------
    # GET: build accordion rows in canonical order
    # -------------------------
    sections = []

    for section_key, title in CONOPS_SECTIONS:
        sec = sections_by_key.get(section_key)
        if not sec:
            continue

        ok, missing, fix_url_name = _normalize_validation(sec)

        # Build "fix missing info" URL
        fix_url = None
        if fix_url_name == "airspace:waiver_planning_new":
            fix_url = f"{reverse('airspace:waiver_planning_new')}?planning_id={application.planning_id}"
        elif fix_url_name:
            try:
                fix_url = reverse(fix_url_name, args=[application.planning_id])
            except Exception:
                try:
                    fix_url = reverse(fix_url_name)
                except Exception:
                    fix_url = None

        sections.append(
            {
                "key": section_key,
                "title": title,
                "obj": sec,
                "display_content": sec.content or "",
                "ok": ok,
                "missing": missing,
                "fix_url": fix_url,
                "auto_only": section_key in AUTO_ONLY,
            }
        )

    # Progress context
    total_sections = len(sections)
    complete_sections = sum(1 for s in sections if s["ok"])
    percent_complete = int(round((complete_sections / total_sections) * 100)) if total_sections else 0
    locked_sections = sum(1 for s in sections if s["obj"].locked)
    total_words = sum(len((s["obj"].content or "").split()) for s in sections)

    all_ready = bool(sections) and all(s["ok"] for s in sections)
    all_locked = bool(sections) and all(s["obj"].locked for s in sections)
    can_export = all_ready and all_locked  
    aircraft_ctx = planning_aircraft_summary
    
    return render(
        request,
        "airspace/conops_review.html",
        {
            "application": application,
            "sections": sections,
            "total_sections": total_sections,
            "complete_sections": complete_sections,
            "percent_complete": percent_complete,
            "locked_sections": locked_sections,
            "total_words": total_words,
            "all_ready": all_ready,
            "all_locked": all_locked,
            "can_export": can_export,
            "aircraft_ctx": aircraft_ctx
        },
    )






def get_conops_sections(application):
    """
    Build export-ready sections in canonical order using:
      - CONOPS_SECTIONS (order + titles)
      - application.conops_sections (DB content + locked)
    Returns list of dicts compatible with conops_pdf.html
    """
    ensure_conops_sections(application)

    sections_qs = application.conops_sections.all()
    sections_by_key = {s.section_key: s for s in sections_qs}

    out = []
    for section_key, title in CONOPS_SECTIONS:
        sec = sections_by_key.get(section_key)
        if not sec:
            continue

        out.append({
            "key": section_key,
            "title": title,
            "locked": bool(sec.locked),
            # ready/ok: use your validator so PDF respects the same rules
            "ready": bool(_safe_ok(validate_conops_section(sec), sec)),
            # point this at PDF partials (recommended) OR reuse section template if you already have it
            "template": f"airspace/pdf/sections/{section_key}.html",
            "obj": sec,                 # keep reference for templates
            "content": sec.content or "",# convenience
        })

    return out


def _safe_ok(validation_result, section_obj):
    """
    Mirrors your conops_review validator normalization.
    """
    res = validation_result

    if isinstance(res, dict):
        return bool(res.get("ok"))

    if isinstance(res, (list, tuple)) and len(res) >= 1:
        return bool(res[0])

    return bool(getattr(section_obj, "is_complete", True))





@login_required
def conops_pdf_export(request, application_id):
    application = get_object_or_404(WaiverApplication, pk=application_id, user=request.user)

    sections = get_conops_sections(application)

    export_sections = sections

    context = {
        "application": application,
        "planning": application.planning,
        "sections": export_sections,
        "generated_on": timezone.now(),
        "request_user": request.user,
    }

    html_string = render_to_string("airspace/conops_pdf.html", context=context, request=request)
    base_url = request.build_absolute_uri("/")
    pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()

    planning = application.planning
    filename = f"CONOPS_{getattr(planning, 'operation_title', 'Operation')}_{application.pk}.pdf".replace(" ", "_")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response



class AirportAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Airport.objects.none()

        qs = Airport.objects.filter(active=True)

        if self.q:
            q = self.q.strip()
            qs = qs.filter(
                Q(icao__icontains=q) |
                Q(name__icontains=q) |
                Q(city__icontains=q) |
                Q(state__icontains=q)
            )

        return qs.order_by("icao")