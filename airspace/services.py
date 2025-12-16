# airspace/services.py
from __future__ import annotations

from typing import Optional, List, Dict, Any

from django.conf import settings
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
# OPENAI CLIENT
# ==========================================================

def get_openai_client() -> OpenAI:
    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env and settings."
        )
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


# ==========================================================
# WAIVER DESCRIPTION (SHORT FORM – NOT CONOPS)
# ==========================================================

def build_waiver_description_prompt(planning) -> str:
    timeframe_labels = _labels_from_choices(
        planning.timeframe_codes(), TIMEFRAME_CHOICES
    )
    purpose_labels = _labels_from_choices(
        planning.purpose_operations or [], PURPOSE_OPERATIONS_CHOICES
    )
    ground_labels = _labels_from_choices(
        planning.ground_environment or [], GROUND_ENVIRONMENT_CHOICES
    )
    procedure_labels = _labels_from_choices(
        planning.prepared_procedures or [], PREPARED_PROCEDURES_CHOICES
    )

    addr_bits = [
        _clean(planning.street_address),
        _clean(planning.location_city),
        _clean(planning.location_state),
        _clean(planning.zip_code),
    ]
    address = ", ".join(b for b in addr_bits if b)

    date_range = ""
    if planning.start_date and planning.end_date:
        date_range = (
            f"{planning.start_date} to {planning.end_date}"
            if planning.start_date != planning.end_date
            else f"{planning.start_date}"
        )

    data: Dict[str, Any] = {
        "Operation Title": _clean(planning.operation_title),
        "Venue Name": _clean(planning.venue_name),
        "Venue Address": address,
        "Launch Location": _clean(planning.launch_location),
        "Purpose": ", ".join(purpose_labels),
        "Purpose Details": _clean(planning.purpose_operations_details),
        "Dates": date_range,
        "Timeframes": ", ".join(timeframe_labels),
        "Frequency": _clean(planning.frequency),
        "Local Time Zone": _clean(planning.local_time_zone),
        "Airspace Class": _clean(planning.airspace_class),
        "Nearest Airport": _clean(planning.nearest_airport),
        "Operating Radius": _clean(planning.location_radius),
        "Max Altitude AGL": planning.proposed_agl or "",
        "Aircraft": _clean(planning.aircraft_display()),
        "Aircraft Count": planning.aircraft_count or "",
        "RPIC Name": _clean(planning.pilot_display_name()),
        "RPIC Certificate": _clean(planning.pilot_cert_display()),
        "RPIC Flight Hours": planning.pilot_flight_hours or "",
        "Visual Observer": _bool_text(planning.has_visual_observer),
        "Drone Detection": _bool_text(planning.uses_drone_detection),
        "Flight Tracking": _bool_text(planning.uses_flight_tracking),
        "Safety Notes": _clean(planning.safety_features_notes),
        "Ground Environment": ", ".join(ground_labels),
        "Estimated Crowd Size": _clean(planning.estimated_crowd_size),
        "Prepared Procedures": ", ".join(procedure_labels),
        "107.39 OOP Waiver": _bool_text(planning.operates_under_10739),
        "107.145 Moving Vehicles Waiver": _bool_text(planning.operates_under_107145),
    }

    return f"""
    You are writing a SHORT FAA DroneZone "Description of Operations".

    RULES:
    - Exactly 2 paragraphs.
    - Each paragraph 2–4 sentences.
    - No bullets, no headings, no markdown.
    - This is NOT a CONOPS.
    - Use ONLY the DATA below. Do not invent details.

    DATA:
    {data}

    Paragraph 1: What / where / when / flight profile.
    Paragraph 2: Safety posture and waiver dependency.
    """.strip()


def generate_waiver_description_text(planning, *, model=None) -> str:
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

def ensure_conops_sections(application) -> None:
    existing = set(
        application.conops_sections.values_list("section_key", flat=True)
    )

    new_sections = [
        ConopsSection(
            application=application,
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
    # Use your existing choice label helpers where possible
    timeframe_labels = _labels_from_choices(
        planning.timeframe_codes(), TIMEFRAME_CHOICES
    )
    purpose_labels = _labels_from_choices(
        planning.purpose_operations or [], PURPOSE_OPERATIONS_CHOICES
    )
    ground_labels = _labels_from_choices(
        planning.ground_environment or [], GROUND_ENVIRONMENT_CHOICES
    )
    procedure_labels = _labels_from_choices(
        planning.prepared_procedures or [], PREPARED_PROCEDURES_CHOICES
    )

    # Address string
    addr_bits = [
        _clean(getattr(planning, "street_address", "")),
        _clean(getattr(planning, "location_city", "")),
        _clean(getattr(planning, "location_state", "")),
        _clean(getattr(planning, "zip_code", "")),
    ]
    address = ", ".join(b for b in addr_bits if b)

    # Airport + distance (robust formatting)
    airport = getattr(planning, "nearest_airport_ref", None)
    airport_icao = (
        _clean(getattr(airport, "icao", ""))
        or _clean(getattr(planning, "nearest_airport", ""))
        or "TBD"
    )
    airport_name = _clean(getattr(airport, "name", "")) or "TBD"
    distance_nm = getattr(planning, "distance_to_airport_nm", None)
    distance_nm_label = str(distance_nm) if distance_nm is not None else "TBD"

    # ARTCC (from Airport reference data, if present)
    # NOTE: field names depend on your Airport model/import mapping.
    # These getattr() calls are safe even if the fields don't exist yet.
    artcc_name = _clean(getattr(airport, "artcc_name", "")) or _clean(getattr(airport, "artcc", "")) or _clean(getattr(airport, "resp_artcc_name", "")) or "TBD"
    artcc_id = _clean(getattr(airport, "artcc_id", "")) or _clean(getattr(airport, "resp_artcc_id", "")) or "TBD"


    # Section-specific injection (ATC/Comms)
    extra_section_instructions = ""
    if section.section_key == "communications_coordination":
        exact_paragraph = (
            'Airspace authorization for operations within Class C airspace will be requested through the FAA DroneZone system prior to the event. '
            'Flight operations will commence only after authorization is granted. '
            'The Remote Pilot in Command (RPIC) will adhere strictly to all approved operational parameters, including altitude limits, geographic boundaries, and time restrictions. '
            'Any deviation from the approved authorization or direction from Air Traffic Control (ATC) will result in immediate termination of UAS operations.'
        )
    if section.section_key == "operational_area_airspace":
        extra_section_instructions = f"""
    INCLUDE ARTCC RESPONSIBILITY IN THIS SECTION.

    - Reference the responsible ARTCC using:
    - Responsible ARTCC: {artcc_name} ({artcc_id})
    - Nearest Airport: {airport_icao} – {airport_name}
    - Distance to Airport (NM): {distance_nm_label}

    - Keep it factual and tied to controlled airspace coordination context.
    - Do not invent phone numbers or frequencies. If missing, leave as "TBD".
    """.strip()

        extra_section_instructions = f"""
    SPECIAL INSTRUCTIONS FOR THIS SECTION:
    1) INCLUDE THIS EXACT PARAGRAPH VERBATIM (word-for-word) as the FIRST paragraph:
    "{exact_paragraph}"

    2) Then add ATC / FACILITY CONTEXT using ONLY these values:
    - Nearest Airport: {airport_icao} – {airport_name}
    - Distance to Airport (NM): {distance_nm_label}
    - Responsible ARTCC: {artcc_name} ({artcc_id})

    3) Then include these operational rules (FAA tone is fine; do not invent extra methods):
    - RPIC will contact ATC prior to the start of operations each day and at the conclusion of operations each day.
    - Fly-away will trigger immediate ATC contact, providing last known location, time, and direction of flight.
    """.strip()

        return f"""
    You are writing a professional FAA Concept of Operations (CONOPS) section.

    SECTION: {section.title}
    SECTION KEY: {section.section_key}

    RULES:
    - Write in formal FAA language.
    - Use short paragraphs; bullets are allowed only when appropriate.
    - Do NOT invent details. If data is missing, write "TBD" and keep it brief.
    - This output must be ONLY the body text for this section (no headings).

    {extra_section_instructions}

    PLANNING DATA:
    Operation Title: {_clean(getattr(planning, "operation_title", "")) or "TBD"}
    Dates: {planning.start_date} to {planning.end_date or planning.start_date}
    Timeframes: {", ".join(timeframe_labels) or "TBD"}
    Frequency: {_clean(getattr(planning, "frequency", "")) or "TBD"}
    Local Time Zone: {_clean(getattr(planning, "local_time_zone", "")) or "TBD"}
    Max Altitude AGL: {getattr(planning, "proposed_agl", None) or "TBD"}

    Venue Name: {_clean(getattr(planning, "venue_name", "")) or "TBD"}
    Address: {address or "TBD"}
    Launch Location: {_clean(getattr(planning, "launch_location", "")) or "TBD"}
    Latitude/Longitude: {getattr(planning, "location_latitude", None) or "TBD"}, {getattr(planning, "location_longitude", None) or "TBD"}
    Operational Radius: {_clean(getattr(planning, "location_radius", "")) or "TBD"}
    Airspace Class: {_clean(getattr(planning, "airspace_class", "")) or "TBD"}
    Nearest Airport (ICAO): {airport_icao}
    Nearest Airport Name: {airport_name}
    Distance to Airport (NM): {distance_nm_label}
    Responsible ARTCC: {artcc_name} ({artcc_id})


    Aircraft: {_clean(planning.aircraft_display()) or "TBD"}
    Aircraft Count: {_clean(getattr(planning, "aircraft_count", "")) or "TBD"}
    Flight Duration: {_clean(getattr(planning, "flight_duration", "")) or "TBD"}
    Flights Per Day: {getattr(planning, "flights_per_day", None) or "TBD"}

    RPIC Name: {_clean(planning.pilot_display_name()) or "TBD"}
    RPIC Certificate: {_clean(planning.pilot_cert_display()) or "TBD"}
    RPIC Flight Hours: {getattr(planning, "pilot_flight_hours", None) or "TBD"}

    Visual Observer Used: {_bool_text(getattr(planning, "has_visual_observer", False))}

    Purpose of Operations: {", ".join(purpose_labels) or "TBD"}
    Purpose Details: {_clean(getattr(planning, "purpose_operations_details", "")) or "TBD"}

    Ground Environment: {", ".join(ground_labels) or "TBD"}
    Ground Environment Other: {_clean(getattr(planning, "ground_environment_other", "")) or "TBD"}
    Estimated Crowd Size: {_clean(getattr(planning, "estimated_crowd_size", "")) or "TBD"}

    Drone Detection Used: {_bool_text(getattr(planning, "uses_drone_detection", False))}
    Flight Tracking Used: {_bool_text(getattr(planning, "uses_flight_tracking", False))}
    Safety Features Notes: {_clean(getattr(planning, "safety_features_notes", "")) or "TBD"}
    Prepared Procedures: {", ".join(procedure_labels) or "TBD"}

    Operating under §107.39 waiver: {_bool_text(getattr(planning, "operates_under_10739", False))}
    107.39 Waiver Number: {_clean(getattr(planning, "oop_waiver_number", "")) or "TBD"}
    Operating under §107.145 waiver: {_bool_text(getattr(planning, "operates_under_107145", False))}
    107.145 Waiver Number: {_clean(getattr(planning, "mv_waiver_number", "")) or "TBD"}

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




def validate_conops_section(section) -> dict:
    """
    Data-driven section validation.
    Returns:
      {"ok": bool, "missing": [str], "fix_url": "airspace:waiver_planning_new"}
    """
    application = section.application
    planning = application.planning
    key = section.section_key

    missing: List[str] = []

    def _has_text(v) -> bool:
        return bool((v or "").strip())

    def _has_any(*vals) -> bool:
        return any(_has_text(v) for v in vals)

    def _has_coords() -> bool:
        return planning.location_latitude is not None and planning.location_longitude is not None

    def _require(label: str, condition: bool):
        if not condition:
            missing.append(label)

    # -------------------------
    # Required planning fields per section
    # -------------------------
    if key == "cover_page":
        _require("Operation title", _has_text(planning.operation_title))
        _require("Start date", bool(planning.start_date))
        _require("Location (venue/address/city)", _has_any(planning.venue_name, planning.street_address, planning.location_city))
        _require("Pilot name", _has_text(planning.pilot_display_name()))
        _require("Pilot certificate number", _has_text(planning.pilot_cert_display()))
        _require("Approximate UAS flight hours", planning.pilot_flight_hours is not None)
        _require("Aircraft", _has_text(planning.aircraft_display()))

    elif key == "purpose_of_operations":
        _require("Purpose of operations (select at least one)", bool(planning.purpose_operations))
        _require("Purpose details (recommended for clarity)", _has_text(planning.purpose_operations_details))

    elif key == "scope_of_operations":
        _require("Timeframe (select at least one)", bool(planning.timeframe))
        _require("Frequency", _has_text(planning.frequency))
        _require("Max altitude AGL", planning.proposed_agl is not None)
        _require("Operational radius", _has_text(planning.location_radius))

    elif key == "operational_area_airspace":
        # accept either coords OR address+zip
        _require("Latitude/Longitude OR Street Address + ZIP", _has_coords() or (_has_text(planning.street_address) and _has_text(planning.zip_code)))
        _require("Airspace class", _has_text(planning.airspace_class))
        _require("Operational radius", _has_text(planning.location_radius))
        _require("Nearest airport (recommended)", _has_text(planning.nearest_airport))

    elif key == "aircraft_equipment":
        _require("Aircraft", _has_text(planning.aircraft_display()))
        _require("Safety features notes", _has_text(planning.safety_features_notes))

    elif key == "crew_roles_responsibilities":
        _require("Pilot name", _has_text(planning.pilot_display_name()))
        _require("Pilot certificate number", _has_text(planning.pilot_cert_display()))
        _require("Pilot flight hours", planning.pilot_flight_hours is not None)
        # VO names removed from model; just require yes/no already exists
        _require("VO usage selected (yes/no)", planning.has_visual_observer in (True, False))

    elif key == "concept_of_operations":
        _require("Location (venue/address/city)", _has_any(planning.venue_name, planning.street_address, planning.location_city))
        _require("Launch location", _has_text(planning.launch_location))
        _require("Aircraft", _has_text(planning.aircraft_display()))
        _require("Flight duration", _has_text(planning.flight_duration))
        _require("Flights per day", planning.flights_per_day is not None)

    elif key == "ground_operations":
        _require("Launch location", _has_text(planning.launch_location))
        _require("Prepared procedures (select at least one)", bool(planning.prepared_procedures))

    elif key == "communications_coordination":
        # Since Airspace CONOPS are for controlled airspace, make sure we can
        # reference the controlling facility context in the generated text.
        _require("Airspace class", _has_text(planning.airspace_class))
        _require("Nearest airport", _has_text(planning.nearest_airport) or bool(getattr(planning, "nearest_airport_ref_id", None)))
        _require("Distance to airport (NM)", getattr(planning, "distance_to_airport_nm", None) is not None)

    # Optional (only enforce if your Airport model actually has these fields)
    airport = getattr(planning, "nearest_airport_ref", None)
    if airport is not None:
        if hasattr(airport, "artcc_name") and hasattr(airport, "artcc_id"):
            _require("ARTCC name (recommended)", _has_text(getattr(airport, "artcc_name", "")))
            _require("ARTCC ID (recommended)", _has_text(getattr(airport, "artcc_id", "")))


    elif key == "safety_systems_risk_mitigation":
        _require("Safety features notes", _has_text(planning.safety_features_notes))
        _require("Prepared procedures (select at least one)", bool(planning.prepared_procedures))

    elif key == "operational_limitations":
        _require("Max altitude AGL", planning.proposed_agl is not None)
        _require("Airspace class", _has_text(planning.airspace_class))
        _require("Timeframe (select at least one)", bool(planning.timeframe))

    elif key == "emergency_contingency":
        _require("Prepared procedures (select at least one)", bool(planning.prepared_procedures))

    elif key == "compliance_statement":
        # Only required if they checked these
        if planning.operates_under_10739:
            _require("107.39 waiver number or waiver document", bool(planning.oop_waiver_number) or bool(planning.oop_waiver_document_id))
        if planning.operates_under_107145:
            _require("107.145 waiver number or waiver document", bool(planning.mv_waiver_number) or bool(planning.mv_waiver_document_id))

    elif key == "appendices":
        # don’t block
        pass

    # -------------------------
    # Content quality gate (optional but useful)
    # -------------------------
    text = (section.content or "").strip()
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
        "fix_url": "airspace:waiver_planning_new",  # your edit flow uses ?planning_id=
    }






def generate_conops_section_text(*, application, section, model=None) -> str:
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
    # include updated_at so auto_now isn't skipped due to update_fields
    section.save(update_fields=["content", "generated_at", "updated_at"])

    validate_conops_section(section)
    return result





def planning_aircraft_summary(planning) -> dict:
    """
    Returns normalized aircraft strings for narrative sections.
    """
    primary = ""
    if getattr(planning, "aircraft", None):
        # Use your Equipment __str__ or build brand/model explicitly
        primary = str(planning.aircraft).strip()

    manual_raw = (getattr(planning, "aircraft_manual", "") or "").strip()

    # Split on commas / newlines; keep it forgiving
    manual_list = []
    if manual_raw:
        parts = manual_raw.replace("\n", ",").split(",")
        manual_list = [p.strip() for p in parts if p.strip()]

    # Dedupe (case-insensitive)
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
