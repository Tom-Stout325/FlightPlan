# airspace/services.py
from __future__ import annotations

from typing import Optional, List, Dict, Any
import re 
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from openai import OpenAI

from .constants.conops import CONOPS_SECTIONS
from .models import ConopsSection
from .forms import (
    TIMEFRAME_CHOICES,
    PURPOSE_OPERATIONS_CHOICES,
    GROUND_ENVIRONMENT_CHOICES,
    PREPARED_PROCEDURES_CHOICES,
)

# ==========================================================
# USER-SCOPING GUARDS
# ==========================================================


def _assert_owned_planning(planning: Any, user: Any) -> None:
    if planning is None or user is None:
        raise PermissionDenied("Unauthorized.")
    if getattr(planning, "user_id", None) != getattr(user, "id", None):
        raise PermissionDenied("You do not have permission to access this waiver planning record.")


def _assert_owned_application(application: Any, user: Any) -> None:
    if application is None or user is None:
        raise PermissionDenied("Unauthorized.")
    if getattr(application, "user_id", None) != getattr(user, "id", None):
        raise PermissionDenied("You do not have permission to access this waiver application.")


def _assert_owned_section(section: Any, user: Any) -> None:
    if section is None or user is None:
        raise PermissionDenied("Unauthorized.")
    app = getattr(section, "application", None)
    if app is None:
        raise PermissionDenied("Unauthorized.")
    if getattr(app, "user_id", None) != getattr(user, "id", None):
        raise PermissionDenied("You do not have permission to access this CONOPS section.")


# ==========================================================
# OPENAI CLIENT
# ==========================================================


def get_openai_client() -> OpenAI:
    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env and settings.")
    return OpenAI(api_key=api_key)


# ==========================================================
# SHARED HELPERS
# ==========================================================


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def _bool_text(value: bool) -> str:
    return "Yes" if bool(value) else "No"


def _labels_from_choices(values: List[str], choices: List[tuple]) -> List[str]:
    if not values:
        return []
    mapping = dict(choices)
    return [mapping.get(v, v) for v in values if v]


def _has_text(v: Any) -> bool:
    return bool((v or "").strip()) if isinstance(v, str) else bool(v)


def _has_aircraft(planning: Any, section: Any) -> bool:
    """
    True if aircraft is present via FK/manual OR already appears in generated section text.
    (The text fallback is intentionally forgiving because OpenAI phrasing varies.)
    """
    if getattr(planning, "aircraft_id", None):
        return True
    if _has_text(getattr(planning, "aircraft_manual", "")):
        return True

    text = (getattr(section, "content", "") or "").lower()
    return any(label in text for label in (
        "unmanned aircraft system",
        "aircraft:",
        "uas",
        "drone:",
    ))


def _has_flight_hours(planning: Any, section: Any) -> bool:
    hours = getattr(planning, "pilot_flight_hours", None)
    if hours not in (None, ""):
        return True
    return "flight hour" in ((getattr(section, "content", "") or "").lower())


def _has_pilot_name(planning: Any, section: Any) -> bool:
    """
    True if pilot name exists via planning OR already appears in generated section text.
    """
    if _has_text(getattr(planning, "pilot_display_name", lambda: "")()):
        return True

    text = (getattr(section, "content", "") or "").strip()
    if not text:
        return False

    patterns = [
        r"Remote Pilot in Command\s*:\s*\S+",
        r"RPIC Name\s*:\s*\S+",
        r"RPIC\s*:\s*\S+",
    ]
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def _line(label: str, value: Any) -> str:
    """
    Render 'Label: value' only if value is present.
    """
    if value is None:
        return ""
    if isinstance(value, str) and not value.strip():
        return ""
    return f"{label}: {value}\n"


def _date_range(planning: Any) -> str:
    start = getattr(planning, "start_date", None)
    end = getattr(planning, "end_date", None)
    if not start:
        return ""
    if end and end != start:
        return f"{start} to {end}"
    return f"{start}"


# ==========================================================
# CONTROLLED AIRSPACE REQUIREMENTS (FAA WAIVER DESCRIPTION)
# ==========================================================

CONTROLLED_AIRSPACE_CLASSES = {"B", "C", "D", "E"}

def _has_text(v: Any) -> bool:
    return bool((v or "").strip()) if isinstance(v, str) else bool(v)

def _is_controlled_airspace(planning: Any) -> bool:
    return (getattr(planning, "airspace_class", "") or "").strip().upper() in CONTROLLED_AIRSPACE_CLASSES

def validate_controlled_airspace_description_requirements(planning: Any) -> None:
    """
    Enforces that the FAA DroneZone Description-of-Operations Paragraph 2 can be written
    WITHOUT inventing details when the operation is in controlled airspace.

    Raises ValidationError with field-specific errors for use in forms/views.
    Uses WaiverPlanning field names EXACTLY as in your model.
    """
    if not _is_controlled_airspace(planning):
        return

    errors: Dict[str, List[str]] = {}

    def add(field: str, msg: str) -> None:
        errors.setdefault(field, []).append(msg)

    # -------------------------
    # Containment (must exist)
    # -------------------------
    if not _has_text(getattr(planning, "operation_area_type", "")):
        add("operation_area_type", "Required for controlled airspace: define the operation area type (radius/corridor/polygon/site).")

    containment_ok = (
        _has_text(getattr(planning, "containment_method", "")) or
        _has_text(getattr(planning, "containment_notes", ""))
    )
    if not containment_ok:
        add("containment_method", "Required for controlled airspace: choose a containment method or provide containment notes.")
        add("containment_notes", "Required for controlled airspace: describe how containment is enforced/verified on-site (no inventing).")

    # If corridor is chosen, require corridor dimensions
    if (getattr(planning, "operation_area_type", "") or "").strip() == "corridor":
        if getattr(planning, "corridor_length_ft", None) is None:
            add("corridor_length_ft", "Required when operation area type is 'corridor': provide corridor length (ft).")
        if getattr(planning, "corridor_width_ft", None) is None:
            add("corridor_width_ft", "Required when operation area type is 'corridor': provide corridor width (ft).")

    # -------------------------
    # ATC coordination (must exist)
    # -------------------------
    # Accept a few ways to satisfy "ATC coordination exists" without inventing:
    # - facility name OR
    # - check-in procedure OR
    # - coordination method with at least one contact channel (phone/frequency)
    atc_facility_name = getattr(planning, "atc_facility_name", "")
    atc_checkin = getattr(planning, "atc_checkin_procedure", "")
    atc_method = getattr(planning, "atc_coordination_method", "")
    atc_phone = getattr(planning, "atc_phone", "")
    atc_freq = getattr(planning, "atc_frequency", "")

    atc_ok = (
        _has_text(atc_facility_name) or
        _has_text(atc_checkin) or
        (_has_text(atc_method) and (_has_text(atc_phone) or _has_text(atc_freq)))
    )
    if not atc_ok:
        add("atc_facility_name", "Required for controlled airspace: provide ATC facility name OR a check-in procedure OR a coordination method with phone/frequency.")
        add("atc_checkin_procedure", "Required for controlled airspace: describe check-in / coordination steps (when/how, what info, and termination procedure).")
        add("atc_coordination_method", "Required for controlled airspace if you don’t have a facility name/check-in procedure: select phone/radio/both/other.")
        add("atc_phone", "Provide if coordination uses phone.")
        add("atc_frequency", "Provide if coordination uses radio.")

    # Deviation/termination triggers (this is how we avoid inventing “traffic abort” logic)
    if not _has_text(getattr(planning, "atc_deviation_triggers", "")):
        add("atc_deviation_triggers", "Required for controlled airspace: define deviation/termination triggers (traffic, weather, direction, etc.).")

    # -------------------------
    # Lost link / flyaway (must exist)
    # -------------------------
    if not _has_text(getattr(planning, "lost_link_behavior", "")):
        add("lost_link_behavior", "Required for controlled airspace: select lost-link behavior (RTH/hover/land).")

    if not _has_text(getattr(planning, "lost_link_actions", "")):
        add("lost_link_actions", "Required for controlled airspace: provide step-by-step lost-link actions (who does what, who is notified, and how ops terminate).")

    # If behavior is RTH, require RTH altitude
    if (getattr(planning, "lost_link_behavior", "") or "").strip() == "rth":
        if getattr(planning, "rth_altitude_ft_agl", None) is None:
            add("rth_altitude_ft_agl", "Required when lost-link behavior is RTH: provide RTH altitude (ft AGL).")

    # Flyaway actions are strongly recommended; require in controlled airspace so Paragraph 2 can be complete.
    if not _has_text(getattr(planning, "flyaway_actions", "")):
        add("flyaway_actions", "Required for controlled airspace: provide flyaway actions (tracking/last-known position capture and facility notification).")

    # -------------------------
    # Finalize
    # -------------------------
    if errors:
        # Raise with field-specific errors so forms can display nicely
        raise ValidationError(errors)
# ==========================================================
# WAIVER DESCRIPTION (SHORT FORM – NOT CONOPS)
# ==========================================================


def build_waiver_description_prompt(planning) -> str:
    timeframe_labels = _labels_from_choices(planning.timeframe_codes(), TIMEFRAME_CHOICES)
    purpose_labels = _labels_from_choices(getattr(planning, "purpose_operations", []) or [], PURPOSE_OPERATIONS_CHOICES)
    ground_labels = _labels_from_choices(getattr(planning, "ground_environment", []) or [], GROUND_ENVIRONMENT_CHOICES)
    procedure_labels = _labels_from_choices(getattr(planning, "prepared_procedures", []) or [], PREPARED_PROCEDURES_CHOICES)

    addr_bits = [
        _clean(getattr(planning, "street_address", "")),
        _clean(getattr(planning, "location_city", "")),
        _clean(getattr(planning, "location_state", "")),
        _clean(getattr(planning, "zip_code", "")),
    ]
    address = ", ".join(b for b in addr_bits if b)

    airport = getattr(planning, "nearest_airport_ref", None)
    airport_icao = _clean(getattr(airport, "icao", "")) or _clean(getattr(planning, "nearest_airport", ""))
    airport_name = _clean(getattr(airport, "name", ""))

    data: Dict[str, Any] = {
        # --- operation basics ---
        "operation_title": _clean(getattr(planning, "operation_title", "")),
        "start_date": getattr(planning, "start_date", None) or "",
        "end_date": getattr(planning, "end_date", None) or "",
        "date_range": _date_range(planning),
        "timeframe": ", ".join(timeframe_labels),
        "frequency": _clean(getattr(planning, "frequency", "")),
        "local_time_zone": _clean(getattr(planning, "local_time_zone", "")),
        "proposed_agl": getattr(planning, "proposed_agl", None) or "",

        # --- location / airspace ---
        "venue_name": _clean(getattr(planning, "venue_name", "")),
        "street_address": _clean(getattr(planning, "street_address", "")),
        "location_city": _clean(getattr(planning, "location_city", "")),
        "location_state": _clean(getattr(planning, "location_state", "")),
        "zip_code": _clean(getattr(planning, "zip_code", "")),
        "venue_address_compiled": address,
        "location_latitude": getattr(planning, "location_latitude", None) or "",
        "location_longitude": getattr(planning, "location_longitude", None) or "",
        "airspace_class": _clean(getattr(planning, "airspace_class", "")),
        "location_radius": _clean(getattr(planning, "location_radius", "")),
        "nearest_airport": _clean(getattr(planning, "nearest_airport", "")),
        "nearest_airport_ref__icao": airport_icao,
        "nearest_airport_ref__name": airport_name,
        "distance_to_airport_nm": getattr(planning, "distance_to_airport_nm", None) or "",

        # --- aircraft ---
        "aircraft": _clean(getattr(planning, "aircraft_display", lambda: "")()),
        "aircraft_count": _clean(getattr(planning, "aircraft_count", "")),

        # --- pilot ---
        "pilot_name": _clean(getattr(planning, "pilot_display_name", lambda: "")()),
        "pilot_cert": _clean(getattr(planning, "pilot_cert_display", lambda: "")()),
        "pilot_flight_hours": getattr(planning, "pilot_flight_hours", None) or "",

        # --- safety posture helpers ---
        "has_visual_observer": _bool_text(getattr(planning, "has_visual_observer", False)),
        "uses_drone_detection": _bool_text(getattr(planning, "uses_drone_detection", False)),
        "uses_flight_tracking": _bool_text(getattr(planning, "uses_flight_tracking", False)),
        "safety_features_notes": _clean(getattr(planning, "safety_features_notes", "")),
        "ground_environment": ", ".join(ground_labels),
        "estimated_crowd_size": _clean(getattr(planning, "estimated_crowd_size", "")),
        "prepared_procedures": ", ".join(procedure_labels),

        # --- waivers (only if you’re also running them for this op) ---
        "operates_under_10739": _bool_text(getattr(planning, "operates_under_10739", False)),
        "oop_waiver_number": _clean(getattr(planning, "oop_waiver_number", "")),
        "operates_under_107145": _bool_text(getattr(planning, "operates_under_107145", False)),
        "mv_waiver_number": _clean(getattr(planning, "mv_waiver_number", "")),

        # --- FAA specificity (controlled airspace waiver posture) ---
        "operation_area_type": _clean(getattr(planning, "operation_area_type", "")),
        "containment_method": _clean(getattr(planning, "containment_method", "")),
        "containment_notes": _clean(getattr(planning, "containment_notes", "")),
        "corridor_length_ft": getattr(planning, "corridor_length_ft", None) or "",
        "corridor_width_ft": getattr(planning, "corridor_width_ft", None) or "",
        "max_groundspeed_mph": getattr(planning, "max_groundspeed_mph", None) or "",

        # --- lost-link / flyaway ---
        "lost_link_behavior": _clean(getattr(planning, "lost_link_behavior", "")),
        "rth_altitude_ft_agl": getattr(planning, "rth_altitude_ft_agl", None) or "",
        "lost_link_actions": _clean(getattr(planning, "lost_link_actions", "")),
        "flyaway_actions": _clean(getattr(planning, "flyaway_actions", "")),

        # --- ATC coordination (facility specifics) ---
        "atc_facility_name": _clean(getattr(planning, "atc_facility_name", "")),
        "atc_coordination_method": _clean(getattr(planning, "atc_coordination_method", "")),
        "atc_phone": _clean(getattr(planning, "atc_phone", "")),
        "atc_frequency": _clean(getattr(planning, "atc_frequency", "")),
        "atc_checkin_procedure": _clean(getattr(planning, "atc_checkin_procedure", "")),
        "atc_deviation_triggers": _clean(getattr(planning, "atc_deviation_triggers", "")),

        # --- weather + crew discipline ---
        "max_wind_mph": getattr(planning, "max_wind_mph", None) or "",
        "min_visibility_sm": getattr(planning, "min_visibility_sm", None) or "",
        "weather_go_nogo": _clean(getattr(planning, "weather_go_nogo", "")),
        "crew_count": getattr(planning, "crew_count", None) or "",
        "crew_briefing_procedure": _clean(getattr(planning, "crew_briefing_procedure", "")),
        "radio_discipline": _clean(getattr(planning, "radio_discipline", "")),
    }

    return f"""
You are writing a SHORT FAA DroneZone "Description of Operations" for controlled airspace waiver review.

RULES:
- Exactly 2 paragraphs.
- Each paragraph 2–4 sentences.
- No bullets, no headings, no markdown.
- This is NOT a CONOPS.
- Use ONLY the DATA below. Do not invent details.

DATA:
{data}

Paragraph 1: Describe the operation, location, dates/times, airspace class, altitude, aircraft, and general flight profile.

Paragraph 2: Describe the safety posture using ONLY provided data.
If present, include:
- Containment (operation_area_type, containment_method, containment_notes, corridor_* if applicable)
- ATC coordination (atc_facility_name, atc_coordination_method, atc_checkin_procedure, atc_deviation_triggers)
- Lost-link and flyaway (lost_link_behavior, rth_altitude_ft_agl, lost_link_actions, flyaway_actions)
- Traffic abort/termination triggers ONLY if explicitly provided in the data (atc_deviation_triggers)
Do not speculate or add procedures that are not explicitly provided.
""".strip()


def generate_waiver_description_text(planning, *, user, model=None) -> str:
    _assert_owned_planning(planning, user)

    # HARD STOP: prevent Paragraph 2 from being forced to "invent" controlled-airspace specifics
    validate_controlled_airspace_description_requirements(planning)
    
    client = get_openai_client()
    prompt = build_waiver_description_prompt(planning)

    response = client.responses.create(
        model=model or getattr(settings, "OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
        input=prompt,
        max_output_tokens=1200,
        text={"format": {"type": "text"}},
    )

    result = (response.output_text or "").strip()
    if not result:
        raise RuntimeError("OpenAI response.output_text was empty.")
    return result


# ==========================================================
# CONOPS INITIALIZATION
# ==========================================================


def ensure_conops_sections(application, *, user) -> None:
    _assert_owned_application(application, user)

    existing = set(application.conops_sections.values_list("section_key", flat=True))

    new_sections = [
        ConopsSection(
            application=application,
            user=application.user,
            section_key=key,
            title=title,
        )
        for key, title in CONOPS_SECTIONS
        if key not in existing
    ]

    if new_sections:
        ConopsSection.objects.bulk_create(new_sections)


# ==========================================================
# CONOPS GENERATION (PER SECTION)
# ==========================================================


def build_conops_section_prompt(*, application, planning, section) -> str:
    """
    Builds the prompt for ANY CONOPS section.

    NOTE: Omits empty fields entirely (no "TBD" lines) to keep the CONOPS clean.
    """

    # ---- Cover Page: label-only output ----
    if section.section_key == "cover_page":
        aircraft = _clean(getattr(planning, "aircraft_display", lambda: "")())
        pilot_name = _clean(getattr(planning, "pilot_display_name", lambda: "")())
        pilot_cert = _clean(getattr(planning, "pilot_cert_display", lambda: "")())
        pilot_hours = getattr(planning, "pilot_flight_hours", None)

        cover_block = (
            _line("Unmanned Aircraft System", aircraft)
            + _line("Remote Pilot in Command", pilot_name)
            + _line("RPIC Certificate", pilot_cert)
            + _line("RPIC Flight Hours", pilot_hours)
            + _line(
                "Location",
                ", ".join([p for p in [
                    _clean(getattr(planning, "venue_name", "")),
                    _clean(getattr(planning, "street_address", "")),
                    _clean(getattr(planning, "location_city", "")),
                    _clean(getattr(planning, "location_state", "")),
                    _clean(getattr(planning, "zip_code", "")),
                ] if p])
            )
            + _line("Dates", _date_range(planning))
            + _line("Airspace Class", _clean(getattr(planning, "airspace_class", "")))
            + _line("Nearest Airport", _clean(getattr(planning, "nearest_airport", "")))
        ).strip()

        return f"""
You are generating the CONOPS Cover Page section.

OUTPUT RULES (MUST FOLLOW):
- Output ONLY the label lines provided in PLANNING DATA.
- Do NOT add paragraphs, explanations, or extra sentences.
- Do NOT reword labels.
- Do NOT invent or infer missing values.
- If a line is not present in PLANNING DATA, omit it.

PLANNING DATA:
{cover_block}
""".strip()

    # ---- Choice label helpers ----
    timeframe_labels = _labels_from_choices(planning.timeframe_codes(), TIMEFRAME_CHOICES)
    purpose_labels = _labels_from_choices(getattr(planning, "purpose_operations", []) or [], PURPOSE_OPERATIONS_CHOICES)
    ground_labels = _labels_from_choices(getattr(planning, "ground_environment", []) or [], GROUND_ENVIRONMENT_CHOICES)
    procedure_labels = _labels_from_choices(getattr(planning, "prepared_procedures", []) or [], PREPARED_PROCEDURES_CHOICES)

    # ---- Address string ----
    addr_bits = [
        _clean(getattr(planning, "street_address", "")),
        _clean(getattr(planning, "location_city", "")),
        _clean(getattr(planning, "location_state", "")),
        _clean(getattr(planning, "zip_code", "")),
    ]
    address = ", ".join(b for b in addr_bits if b)

    # ---- Airport + distance ----
    airport = getattr(planning, "nearest_airport_ref", None)
    airport_icao = _clean(getattr(airport, "icao", "")) or _clean(getattr(planning, "nearest_airport", ""))
    airport_name = _clean(getattr(airport, "name", ""))

    distance_nm = getattr(planning, "distance_to_airport_nm", None)

    # ---- ARTCC (safe; your Airport model may not have these fields yet) ----
    artcc_name = (
        _clean(getattr(airport, "artcc_name", ""))
        or _clean(getattr(airport, "artcc", ""))
        or _clean(getattr(airport, "resp_artcc_name", ""))
    )
    artcc_id = (
        _clean(getattr(airport, "artcc_id", ""))
        or _clean(getattr(airport, "resp_artcc_id", ""))
    )

    # ==========================================================
    # Section-specific instructions
    # ==========================================================
    extra_section_instructions = ""

    if section.section_key == "communications_coordination":
        extra_section_instructions = """
SPECIAL INSTRUCTIONS FOR THIS SECTION:
- Focus on controlled airspace coordination and communication discipline.
- Use ONLY the ATC/Facility details provided in PLANNING DATA.
- If atc_facility_name / atc_coordination_method is blank, do not invent facility names, frequencies, phone numbers, or procedures.
- Include atc_checkin_procedure and atc_deviation_triggers only if present.
- Keep it procedural (who does what, when, and how), not promotional.
""".strip()

    elif section.section_key == "emergency_contingency":
        extra_section_instructions = """
SPECIAL INSTRUCTIONS FOR THIS SECTION:
- Write step-by-step emergency and contingency procedures using ONLY provided planning data.
- If present, include:
  - lost_link_behavior and rth_altitude_ft_agl
  - lost_link_actions and flyaway_actions
  - atc_coordination_method + atc_facility_name for abnormal events (only if provided)
  - atc_deviation_triggers (only if provided)
  - weather go/no-go criteria (max_wind_mph, min_visibility_sm, weather_go_nogo) only if provided
- Do not add new emergency types, emergency services, frequencies, or check-in rules that are not in the data.
""".strip()

    elif section.section_key == "safety_systems_risk_mitigation":
        extra_section_instructions = """
SPECIAL INSTRUCTIONS FOR THIS SECTION:
- Emphasize concrete risk controls and mitigations appropriate for controlled airspace.
- If present, include: operation_area_type/containment_method/containment_notes, crew_briefing_procedure, radio_discipline,
  and atc_deviation_triggers (only if provided).
- Keep mitigations procedural and verifiable; avoid vague assurances.
""".strip()

    elif section.section_key == "operational_limitations":
        extra_section_instructions = """
SPECIAL INSTRUCTIONS FOR THIS SECTION:
- List hard operational limits only (proposed_agl, airspace_class, timeframe, location_radius, corridor dims, max_groundspeed_mph,
  max_wind_mph, min_visibility_sm).
- Use short bullets where appropriate.
- Do not invent numeric thresholds or constraints.
""".strip()

    elif section.section_key == "operational_area_airspace":
        extra_section_instructions = f"""
SPECIAL INSTRUCTIONS FOR THIS SECTION:
- Include responsible ATC context ONLY when present in PLANNING DATA.
- Use ONLY these values (omit anything blank):
  - Responsible ARTCC: {artcc_name or ""} ({artcc_id or ""})
  - Nearest Airport: {airport_icao or ""} – {airport_name or ""}
  - Distance to Airport (NM): {distance_nm if distance_nm is not None else ""}
- Do not invent phone numbers, frequencies, or facility names.
""".strip()

    # ==========================================================
    # Build "only-if-present" blocks (labels match your WaiverPlanning field names)
    # ==========================================================

    operation_block = (
        _line("operation_title", _clean(getattr(planning, "operation_title", "")))
        + _line("start_date", getattr(planning, "start_date", None))
        + _line("end_date", getattr(planning, "end_date", None))
        + _line("timeframe", ", ".join(timeframe_labels) if timeframe_labels else "")
        + _line("frequency", _clean(getattr(planning, "frequency", "")))
        + _line("local_time_zone", _clean(getattr(planning, "local_time_zone", "")))
        + _line("proposed_agl", getattr(planning, "proposed_agl", None))
    )

    location_block = (
        _line("venue_name", _clean(getattr(planning, "venue_name", "")))
        + _line("street_address", _clean(getattr(planning, "street_address", "")))
        + _line("location_city", _clean(getattr(planning, "location_city", "")))
        + _line("location_state", _clean(getattr(planning, "location_state", "")))
        + _line("zip_code", _clean(getattr(planning, "zip_code", "")))
        + _line("address_compiled", address)
        + _line("location_latitude", getattr(planning, "location_latitude", None))
        + _line("location_longitude", getattr(planning, "location_longitude", None))
        + _line("location_radius", _clean(getattr(planning, "location_radius", "")))
        + _line("airspace_class", _clean(getattr(planning, "airspace_class", "")))
        + _line("nearest_airport", _clean(getattr(planning, "nearest_airport", "")))
        + _line("nearest_airport_ref.icao", airport_icao)
        + _line("nearest_airport_ref.name", airport_name)
        + _line("distance_to_airport_nm", distance_nm)
        + _line("responsible_artcc", f"{artcc_name} ({artcc_id})" if (artcc_name or artcc_id) else "")
    )

    aircraft_block = (
        _line("aircraft", _clean(getattr(planning, "aircraft_display", lambda: "")()))
        + _line("aircraft_manual", _clean(getattr(planning, "aircraft_manual", "")))
        + _line("aircraft_count", _clean(getattr(planning, "aircraft_count", "")))
        + _line("flight_duration", _clean(getattr(planning, "flight_duration", "")))
        + _line("flights_per_day", getattr(planning, "flights_per_day", None))
    )

    pilot_block = (
        _line("pilot_name_manual", _clean(getattr(planning, "pilot_name_manual", "")))
        + _line("pilot_cert_manual", _clean(getattr(planning, "pilot_cert_manual", "")))
        + _line("pilot_display_name()", _clean(getattr(planning, "pilot_display_name", lambda: "")()))
        + _line("pilot_cert_display()", _clean(getattr(planning, "pilot_cert_display", lambda: "")()))
        + _line("pilot_flight_hours", getattr(planning, "pilot_flight_hours", None))
        + _line("has_visual_observer", _bool_text(getattr(planning, "has_visual_observer", False)))
    )

    ops_block = (
        _line("purpose_operations", ", ".join(purpose_labels) if purpose_labels else "")
        + _line("purpose_operations_details", _clean(getattr(planning, "purpose_operations_details", "")))
        + _line("ground_environment", ", ".join(ground_labels) if ground_labels else "")
        + _line("ground_environment_other", _clean(getattr(planning, "ground_environment_other", "")))
        + _line("estimated_crowd_size", _clean(getattr(planning, "estimated_crowd_size", "")))
        + _line("uses_drone_detection", _bool_text(getattr(planning, "uses_drone_detection", False)))
        + _line("uses_flight_tracking", _bool_text(getattr(planning, "uses_flight_tracking", False)))
        + _line("safety_features_notes", _clean(getattr(planning, "safety_features_notes", "")))
        + _line("prepared_procedures", ", ".join(procedure_labels) if procedure_labels else "")
    )

    waiver_block = (
        _line("operates_under_10739", _bool_text(getattr(planning, "operates_under_10739", False)))
        + _line("oop_waiver_number", _clean(getattr(planning, "oop_waiver_number", "")))
        + _line("operates_under_107145", _bool_text(getattr(planning, "operates_under_107145", False)))
        + _line("mv_waiver_number", _clean(getattr(planning, "mv_waiver_number", "")))
    )

    containment_block = (
        _line("operation_area_type", _clean(getattr(planning, "operation_area_type", "")))
        + _line("containment_method", _clean(getattr(planning, "containment_method", "")))
        + _line("containment_notes", _clean(getattr(planning, "containment_notes", "")))
        + _line("corridor_length_ft", getattr(planning, "corridor_length_ft", None))
        + _line("corridor_width_ft", getattr(planning, "corridor_width_ft", None))
        + _line("max_groundspeed_mph", getattr(planning, "max_groundspeed_mph", None))
    )

    atc_block = (
        _line("atc_facility_name", _clean(getattr(planning, "atc_facility_name", "")))
        + _line("atc_coordination_method", _clean(getattr(planning, "atc_coordination_method", "")))
        + _line("atc_phone", _clean(getattr(planning, "atc_phone", "")))
        + _line("atc_frequency", _clean(getattr(planning, "atc_frequency", "")))
        + _line("atc_checkin_procedure", _clean(getattr(planning, "atc_checkin_procedure", "")))
        + _line("atc_deviation_triggers", _clean(getattr(planning, "atc_deviation_triggers", "")))
    )

    lost_link_block = (
        _line("lost_link_behavior", _clean(getattr(planning, "lost_link_behavior", "")))
        + _line("rth_altitude_ft_agl", getattr(planning, "rth_altitude_ft_agl", None))
        + _line("lost_link_actions", _clean(getattr(planning, "lost_link_actions", "")))
        + _line("flyaway_actions", _clean(getattr(planning, "flyaway_actions", "")))
    )

    weather_block = (
        _line("max_wind_mph", getattr(planning, "max_wind_mph", None))
        + _line("min_visibility_sm", getattr(planning, "min_visibility_sm", None))
        + _line("weather_go_nogo", _clean(getattr(planning, "weather_go_nogo", "")))
    )

    crew_block = (
        _line("crew_count", getattr(planning, "crew_count", None))
        + _line("crew_briefing_procedure", _clean(getattr(planning, "crew_briefing_procedure", "")))
        + _line("radio_discipline", _clean(getattr(planning, "radio_discipline", "")))
    )

    return f"""
You are writing a professional FAA Concept of Operations (CONOPS) section.

SECTION: {section.title}
SECTION KEY: {section.section_key}

RULES:
- Write in formal FAA language.
- Use short paragraphs; bullets are allowed only when appropriate.
- Do NOT invent details.
- If data is missing, OMIT it entirely (do not write TBD).
- Output must be ONLY the body text for this section (no headings).
- Prefer procedural specificity over general statements when data supports it.

{extra_section_instructions}

PLANNING DATA (only include what is provided below):
{operation_block}
{location_block}
{aircraft_block}
{pilot_block}
{ops_block}
{waiver_block}

{containment_block}
{atc_block}
{lost_link_block}
{weather_block}
{crew_block}

WRITE THE SECTION BODY TEXT ONLY.
""".strip()


# ==========================================================
# CONOPS VALIDATION
# ==========================================================


MIN_WORDS_BY_SECTION = {
    "cover_page": 20,
    "purpose_of_operations": 60,
    "scope_of_operations": 60,
    "operational_area_airspace": 80,
    "aircraft_equipment": 60,
    "crew_roles_responsibilities": 60,
    "concept_of_operations": 120,
    "ground_operations": 60,
    "communications_coordination": 80,
    "safety_systems_risk_mitigation": 80,
    "operational_limitations": 40,
    "emergency_contingency": 80,
    "compliance_statement": 40,
    "appendices": 10,
}


def validate_conops_section(section, *, user) -> dict:
    """
    Data-driven section validation.

    Returns:
      {"ok": bool, "missing": [str], "fix_url": "airspace:waiver_planning_new"}
    """
    _assert_owned_section(section, user)

    application = section.application
    planning = application.planning
    key = section.section_key

    missing: List[str] = []

    def _has_any(*vals) -> bool:
        return any(_has_text(v) for v in vals)

    def _has_coords() -> bool:
        return getattr(planning, "location_latitude", None) is not None and getattr(planning, "location_longitude", None) is not None

    def _require(label: str, condition: bool):
        if not condition:
            missing.append(label)

    # -------------------------
    # Required planning fields per section
    # -------------------------
    if key == "cover_page":
        _require("operation_title", _has_text(getattr(planning, "operation_title", "")))
        _require("start_date", bool(getattr(planning, "start_date", None)))
        _require(
            "venue_name/street_address/location_city (at least one)",
            _has_any(
                getattr(planning, "venue_name", ""),
                getattr(planning, "street_address", ""),
                getattr(planning, "location_city", ""),
            ),
        )
        _require("pilot_display_name()", _has_pilot_name(planning, section))
        _require("pilot_cert_display()", _has_text(getattr(planning, "pilot_cert_display", lambda: "")()))
        _require("pilot_flight_hours", _has_flight_hours(planning, section))
        _require("aircraft", _has_aircraft(planning, section))

    elif key == "purpose_of_operations":
        _require("purpose_operations (select at least one)", bool(getattr(planning, "purpose_operations", None)))
        _require("purpose_operations_details (recommended)", _has_text(getattr(planning, "purpose_operations_details", "")))

    elif key == "scope_of_operations":
        _require("timeframe (select at least one)", bool(getattr(planning, "timeframe", None)))
        _require("frequency", _has_text(getattr(planning, "frequency", "")))
        _require("proposed_agl", getattr(planning, "proposed_agl", None) is not None)
        _require("location_radius", _has_text(getattr(planning, "location_radius", "")))

    elif key == "operational_area_airspace":
        _require(
            "location_latitude/location_longitude OR (street_address + zip_code)",
            _has_coords()
            or (_has_text(getattr(planning, "street_address", "")) and _has_text(getattr(planning, "zip_code", ""))),
        )
        _require("airspace_class", _has_text(getattr(planning, "airspace_class", "")))
        _require("location_radius", _has_text(getattr(planning, "location_radius", "")))
        _require(
            "nearest_airport or nearest_airport_ref",
            _has_text(getattr(planning, "nearest_airport", "")) or bool(getattr(planning, "nearest_airport_ref_id", None)),
        )

    elif key == "aircraft_equipment":
        _require("aircraft/aircraft_manual", _has_aircraft(planning, section))
        _require("safety_features_notes", _has_text(getattr(planning, "safety_features_notes", "")))

    elif key == "crew_roles_responsibilities":
        _require("pilot_display_name()", _has_pilot_name(planning, section))
        _require("pilot_cert_display()", _has_text(getattr(planning, "pilot_cert_display", lambda: "")()))
        _require("pilot_flight_hours", _has_flight_hours(planning, section))
        _require("has_visual_observer (yes/no)", getattr(planning, "has_visual_observer", None) in (True, False))

    elif key == "concept_of_operations":
        _require(
            "venue_name/street_address/location_city (at least one)",
            _has_any(
                getattr(planning, "venue_name", ""),
                getattr(planning, "street_address", ""),
                getattr(planning, "location_city", ""),
            ),
        )
        _require("launch_location", _has_text(getattr(planning, "launch_location", "")))
        _require("aircraft/aircraft_manual", _has_aircraft(planning, section))
        _require("flight_duration", _has_text(getattr(planning, "flight_duration", "")))
        _require("flights_per_day", getattr(planning, "flights_per_day", None) is not None)

    elif key == "ground_operations":
        _require("launch_location", _has_text(getattr(planning, "launch_location", "")))
        _require("prepared_procedures (select at least one)", bool(getattr(planning, "prepared_procedures", None)))

    elif key == "communications_coordination":
        _require("airspace_class", _has_text(getattr(planning, "airspace_class", "")))
        _require(
            "nearest_airport or nearest_airport_ref",
            _has_text(getattr(planning, "nearest_airport", "")) or bool(getattr(planning, "nearest_airport_ref_id", None)),
        )
        _require("distance_to_airport_nm", getattr(planning, "distance_to_airport_nm", None) is not None)

    elif key == "safety_systems_risk_mitigation":
        _require("safety_features_notes", _has_text(getattr(planning, "safety_features_notes", "")))
        _require("prepared_procedures (select at least one)", bool(getattr(planning, "prepared_procedures", None)))

    elif key == "operational_limitations":
        _require("proposed_agl", getattr(planning, "proposed_agl", None) is not None)
        _require("airspace_class", _has_text(getattr(planning, "airspace_class", "")))
        _require("timeframe (select at least one)", bool(getattr(planning, "timeframe", None)))

    elif key == "emergency_contingency":
        _require(
            "lost_link_behavior OR lost_link_actions",
            _has_any(getattr(planning, "lost_link_behavior", ""), getattr(planning, "lost_link_actions", "")),
        )
        _require(
            "flyaway_actions OR atc_deviation_triggers",
            _has_any(getattr(planning, "flyaway_actions", ""), getattr(planning, "atc_deviation_triggers", "")),
        )

    elif key == "compliance_statement":
        if getattr(planning, "operates_under_10739", False):
            _require(
                "oop_waiver_number or oop_waiver_document",
                bool(getattr(planning, "oop_waiver_number", None)) or bool(getattr(planning, "oop_waiver_document_id", None)),
            )
        if getattr(planning, "operates_under_107145", False):
            _require(
                "mv_waiver_number or mv_waiver_document",
                bool(getattr(planning, "mv_waiver_number", None)) or bool(getattr(planning, "mv_waiver_document_id", None)),
            )

    elif key == "appendices":
        pass

    # -------------------------
    # Content quality gate
    # -------------------------
    text = (getattr(section, "content", "") or "").strip()
    min_words = MIN_WORDS_BY_SECTION.get(key, 50)
    word_count = len(text.split()) if text else 0

    if not text:
        missing.append("Section text is empty.")
    elif word_count < min_words:
        missing.append(f"Section text is too short ({word_count} words). Target: {min_words}+.")

    ok = len(missing) == 0

    section.is_complete = ok
    section.validated_at = timezone.now()
    section.save(update_fields=["is_complete", "validated_at", "updated_at"])

    return {
        "ok": ok,
        "missing": missing,
        "fix_url": "airspace:waiver_planning_new",
    }


def generate_conops_section_text(*, application, section, user, model=None) -> str:
    _assert_owned_application(application, user)
    _assert_owned_section(section, user)

    planning = application.planning
    client = get_openai_client()

    prompt = build_conops_section_prompt(
        application=application,
        planning=planning,
        section=section,
    )

    response = client.responses.create(
        model=model or getattr(settings, "OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
        input=prompt,
        max_output_tokens=2000,
        text={"format": {"type": "text"}},
    )

    result = (response.output_text or "").strip()
    if not result:
        raise RuntimeError("OpenAI response.output_text was empty.")

    section.content = result
    section.generated_at = timezone.now()
    section.save(update_fields=["content", "generated_at", "updated_at"])

    validate_conops_section(section, user=user)
    return result


def planning_aircraft_summary(planning, *, user) -> dict:
    """
    Returns normalized aircraft strings for narrative sections.
    """
    _assert_owned_planning(planning, user)

    primary = ""
    if getattr(planning, "aircraft", None):
        primary = str(planning.aircraft).strip()

    manual_raw = (getattr(planning, "aircraft_manual", "") or "").strip()

    manual_list = []
    if manual_raw:
        parts = manual_raw.replace("\n", ",").split(",")
        manual_list = [p.strip() for p in parts if p.strip()]

    seen = set()
    combined = []
    for item in [primary] + manual_list:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        combined.append(item)

    return {
        "primary": primary,
        "manual_list": manual_list,
        "combined_list": combined,
        "combined_display": "; ".join(combined) if combined else "—",
    }
