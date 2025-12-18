# airspace/services.py
from __future__ import annotations

from typing import Optional, List, Dict, Any

from django.conf import settings
from django.utils import timezone
import re
from openai import OpenAI

from .constants.conops import CONOPS_SECTIONS
from .models import ConopsSection
from .forms import (
    TIMEFRAME_CHOICES,
    PURPOSE_OPERATIONS_CHOICES,
    GROUND_ENVIRONMENT_CHOICES,
    PREPARED_PROCEDURES_CHOICES,
    GROUND_ENVIRONMENT_CHOICES,
)


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

    # Accept either of these labels (your UI text uses Remote Pilot in Command)
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


# ==========================================================
# WAIVER DESCRIPTION (SHORT FORM – NOT CONOPS)
# ==========================================================

def build_waiver_description_prompt(planning) -> str:
    timeframe_labels = _labels_from_choices(planning.timeframe_codes(), TIMEFRAME_CHOICES)
    purpose_labels = _labels_from_choices(planning.purpose_operations or [], PURPOSE_OPERATIONS_CHOICES)
    ground_labels = _labels_from_choices(planning.ground_environment or [], GROUND_ENVIRONMENT_CHOICES)
    procedure_labels = _labels_from_choices(planning.prepared_procedures or [], PREPARED_PROCEDURES_CHOICES)

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
    existing = set(application.conops_sections.values_list("section_key", flat=True))

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
    """
    Builds the prompt for ANY CONOPS section. This must always return a string.

    NOTE: This version omits empty fields entirely (no "TBD" lines),
    using _line() blocks so the generated CONOPS stays clean.
    """


    if section.section_key == "cover_page":
        aircraft = _clean(planning.aircraft_display())
        pilot_name = _clean(planning.pilot_display_name())
        pilot_cert = _clean(planning.pilot_cert_display())
        pilot_hours = getattr(planning, "pilot_flight_hours", None)

        # If you want these always present even when missing, change _line -> _line_or_tbd
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
            + _line(
                "Dates",
                f"{getattr(planning, 'start_date', None)}"
                + (f" to {getattr(planning, 'end_date', None)}" if getattr(planning, "end_date", None) else "")
            )
            + _line("Airspace Classification", _clean(getattr(planning, "airspace_class", "")))
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
    purpose_labels = _labels_from_choices(planning.purpose_operations or [], PURPOSE_OPERATIONS_CHOICES)
    ground_labels = _labels_from_choices(planning.ground_environment or [], GROUND_ENVIRONMENT_CHOICES)
    procedure_labels = _labels_from_choices(planning.prepared_procedures or [], PREPARED_PROCEDURES_CHOICES)

    # ---- Address string ----
    addr_bits = [
        _clean(getattr(planning, "street_address", "")),
        _clean(getattr(planning, "location_city", "")),
        _clean(getattr(planning, "location_state", "")),
        _clean(getattr(planning, "zip_code", "")),
    ]
    address = ", ".join(b for b in addr_bits if b)

    # ---- Airport + distance (robust formatting) ----
    airport = getattr(planning, "nearest_airport_ref", None)
    airport_icao = _clean(getattr(airport, "icao", "")) or _clean(getattr(planning, "nearest_airport", ""))
    airport_name = _clean(getattr(airport, "name", ""))

    distance_nm = getattr(planning, "distance_to_airport_nm", None)

    # ---- ARTCC (field names vary; keep safe) ----
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

    if section.section_key == "cover_page":
        extra_section_instructions = """
SPECIAL INSTRUCTIONS FOR THIS SECTION:
- Use these exact labels (verbatim) when present:
  - "Unmanned Aircraft System:"
  - "Remote Pilot in Command:"
  - "RPIC Certificate:"
  - "RPIC Flight Hours:"
  - "Location:"
  - "Dates:"
- Keep it concise and professional (cover-page style).
""".strip()

    elif section.section_key == "communications_coordination":
        exact_paragraph = (
            "Airspace authorization for operations within controlled airspace will be requested through the FAA DroneZone system prior to the event. "
            "Flight operations will commence only after authorization is granted. "
            "The Remote Pilot in Command (RPIC) will adhere strictly to all approved operational parameters, including altitude limits, geographic boundaries, and time restrictions. "
            "Any deviation from the approved authorization or direction from Air Traffic Control (ATC) will result in immediate termination of UAS operations."
        )
        extra_section_instructions = f"""
SPECIAL INSTRUCTIONS FOR THIS SECTION:
1) INCLUDE THIS EXACT PARAGRAPH VERBATIM (word-for-word) as the FIRST paragraph:
"{exact_paragraph}"

2) Then add ATC / FACILITY CONTEXT using ONLY these values (if present):
- Nearest Airport: {airport_icao or ""}
- Nearest Airport Name: {airport_name or ""}
- Distance to Airport (NM): {distance_nm if distance_nm is not None else ""}
- Responsible ARTCC: {artcc_name or ""} ({artcc_id or ""})

3) Then include these operational rules (do not invent extra methods):
- RPIC will contact ATC prior to the start of operations each day and at the conclusion of operations each day.
- Fly-away will trigger immediate ATC contact, providing last known location, time, and direction of flight.
""".strip()

    elif section.section_key == "operational_area_airspace":
        extra_section_instructions = f"""
SPECIAL INSTRUCTIONS FOR THIS SECTION:
- INCLUDE ARTCC RESPONSIBILITY IN THIS SECTION when present.
- Use ONLY these values (leave out anything blank):
  - Responsible ARTCC: {artcc_name or ""} ({artcc_id or ""})
  - Nearest Airport: {airport_icao or ""} – {airport_name or ""}
  - Distance to Airport (NM): {distance_nm if distance_nm is not None else ""}
- Do not invent phone numbers or frequencies.
""".strip()

    # ==========================================================
    # Build "only-if-present" blocks
    # ==========================================================

    # Core operation info
    operation_block = (
        _line("Operation Title", _clean(getattr(planning, "operation_title", "")))
        + _line("Dates", f"{getattr(planning, 'start_date', None)} to {getattr(planning, 'end_date', None) or getattr(planning, 'start_date', None)}"
                if getattr(planning, "start_date", None) else "")
        + _line("Timeframes", ", ".join(timeframe_labels) if timeframe_labels else "")
        + _line("Frequency", _clean(getattr(planning, "frequency", "")))
        + _line("Local Time Zone", _clean(getattr(planning, "local_time_zone", "")))
        + _line("Max Altitude AGL", getattr(planning, "proposed_agl", None))
    )

    # Location / airspace
    location_block = (
        _line("Venue Name", _clean(getattr(planning, "venue_name", "")))
        + _line("Address", address)
        + _line("Launch Location", _clean(getattr(planning, "launch_location", "")))
        + _line("Latitude/Longitude",
                f"{getattr(planning, 'location_latitude', None)}, {getattr(planning, 'location_longitude', None)}"
                if (getattr(planning, "location_latitude", None) is not None and getattr(planning, "location_longitude", None) is not None)
                else "")
        + _line("Operational Radius", _clean(getattr(planning, "location_radius", "")))
        + _line("Airspace Class", _clean(getattr(planning, "airspace_class", "")))
        + _line("Nearest Airport (ICAO)", airport_icao)
        + _line("Nearest Airport Name", airport_name)
        + _line("Distance to Airport (NM)", distance_nm)
        + _line("Responsible ARTCC", f"{artcc_name} ({artcc_id})" if (artcc_name or artcc_id) else "")
    )

    # Aircraft
    aircraft = _clean(planning.aircraft_display())
    aircraft_count = getattr(planning, "aircraft_count", None)
    aircraft_block = (
        _line("Unmanned Aircraft System", aircraft)
        + _line("Aircraft Count", aircraft_count)
        + _line("Flight Duration", _clean(getattr(planning, "flight_duration", "")))
        + _line("Flights Per Day", getattr(planning, "flights_per_day", None))
    )

    # Pilot
    pilot_name = _clean(planning.pilot_display_name())
    pilot_cert = _clean(planning.pilot_cert_display())
    pilot_hours = getattr(planning, "pilot_flight_hours", None)

    # Use "Remote Pilot in Command" label for cover-page friendliness
    pilot_name_label = "Remote Pilot in Command" if section.section_key == "cover_page" else "RPIC Name"

    pilot_block = (
        _line(pilot_name_label, pilot_name)
        + _line("RPIC Certificate", pilot_cert)
        + _line("RPIC Flight Hours", pilot_hours)
        + _line("Visual Observer Used", _bool_text(getattr(planning, "has_visual_observer", False))
                if getattr(planning, "has_visual_observer", None) in (True, False) else "")
    )

    # Ops profile / safety
    ops_block = (
        _line("Purpose of Operations", ", ".join(purpose_labels) if purpose_labels else "")
        + _line("Purpose Details", _clean(getattr(planning, "purpose_operations_details", "")))
        + _line("Ground Environment", ", ".join(ground_labels) if ground_labels else "")
        + _line("Ground Environment Other", _clean(getattr(planning, "ground_environment_other", "")))
        + _line("Estimated Crowd Size", _clean(getattr(planning, "estimated_crowd_size", "")))
        + _line("Drone Detection Used", _bool_text(getattr(planning, "uses_drone_detection", False))
                if getattr(planning, "uses_drone_detection", None) in (True, False) else "")
        + _line("Flight Tracking Used", _bool_text(getattr(planning, "uses_flight_tracking", False))
                if getattr(planning, "uses_flight_tracking", None) in (True, False) else "")
        + _line("Safety Features Notes", _clean(getattr(planning, "safety_features_notes", "")))
        + _line("Prepared Procedures", ", ".join(procedure_labels) if procedure_labels else "")
    )

    # Waivers
    waiver_block = (
        _line("Operating under §107.39 waiver", _bool_text(getattr(planning, "operates_under_10739", False))
              if getattr(planning, "operates_under_10739", None) in (True, False) else "")
        + _line("107.39 Waiver Number", _clean(getattr(planning, "oop_waiver_number", "")))
        + _line("Operating under §107.145 waiver", _bool_text(getattr(planning, "operates_under_107145", False))
              if getattr(planning, "operates_under_107145", None) in (True, False) else "")
        + _line("107.145 Waiver Number", _clean(getattr(planning, "mv_waiver_number", "")))
    )

    # ==========================================================
    # Final prompt
    # ==========================================================
    return f"""
You are writing a professional FAA Concept of Operations (CONOPS) section.

SECTION: {section.title}
SECTION KEY: {section.section_key}

RULES:
- Write in formal FAA language.
- Use short paragraphs; bullets are allowed only when appropriate.
- Do NOT invent details.
- If data is missing, OMIT it entirely (do not write TBD).
- This output must be ONLY the body text for this section (no headings).

{extra_section_instructions}

PLANNING DATA (only include what is provided below):
{operation_block}
{location_block}
{aircraft_block}
{pilot_block}
{ops_block}
{waiver_block}

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
        _require("Operation title", _has_text(getattr(planning, "operation_title", "")))
        _require("Start date", bool(getattr(planning, "start_date", None)))
        _require(
            "Location (venue/address/city)",
            _has_any(
                getattr(planning, "venue_name", ""),
                getattr(planning, "street_address", ""),
                getattr(planning, "location_city", ""),
            ),
        )
        _require("Pilot name", _has_pilot_name(planning, section))

        _require("Pilot certificate number", _has_text(planning.pilot_cert_display()))
        _require("Approximate UAS flight hours", _has_flight_hours(planning, section))
        _require("Aircraft", _has_aircraft(planning, section))

    elif key == "purpose_of_operations":
        _require("Purpose of operations (select at least one)", bool(getattr(planning, "purpose_operations", None)))
        _require("Purpose details (recommended for clarity)", _has_text(getattr(planning, "purpose_operations_details", "")))

    elif key == "scope_of_operations":
        _require("Timeframe (select at least one)", bool(getattr(planning, "timeframe", None)))
        _require("Frequency", _has_text(getattr(planning, "frequency", "")))
        _require("Max altitude AGL", getattr(planning, "proposed_agl", None) is not None)
        _require("Operational radius", _has_text(getattr(planning, "location_radius", "")))

    elif key == "operational_area_airspace":
        _require(
            "Latitude/Longitude OR Street Address + ZIP",
            _has_coords()
            or (_has_text(getattr(planning, "street_address", "")) and _has_text(getattr(planning, "zip_code", ""))),
        )
        _require("Airspace class", _has_text(getattr(planning, "airspace_class", "")))
        _require("Operational radius", _has_text(getattr(planning, "location_radius", "")))
        _require(
            "Nearest airport (recommended)",
            _has_text(getattr(planning, "nearest_airport", "")) or bool(getattr(planning, "nearest_airport_ref_id", None)),
        )

    elif key == "aircraft_equipment":
        _require("Aircraft", _has_aircraft(planning, section))
        _require("Safety features notes", _has_text(getattr(planning, "safety_features_notes", "")))

    elif key == "crew_roles_responsibilities":
        _require("Pilot name", _has_pilot_name(planning, section))

        _require("Pilot certificate number", _has_text(planning.pilot_cert_display()))
        _require("Pilot flight hours", _has_flight_hours(planning, section))
        _require("VO usage selected (yes/no)", getattr(planning, "has_visual_observer", None) in (True, False))

    elif key == "concept_of_operations":
        _require(
            "Location (venue/address/city)",
            _has_any(
                getattr(planning, "venue_name", ""),
                getattr(planning, "street_address", ""),
                getattr(planning, "location_city", ""),
            ),
        )
        _require("Launch location", _has_text(getattr(planning, "launch_location", "")))
        _require("Aircraft", _has_aircraft(planning, section))
        _require("Flight duration", _has_text(getattr(planning, "flight_duration", "")))
        _require("Flights per day", getattr(planning, "flights_per_day", None) is not None)

    elif key == "ground_operations":
        _require("Launch location", _has_text(getattr(planning, "launch_location", "")))
        _require("Prepared procedures (select at least one)", bool(getattr(planning, "prepared_procedures", None)))

    elif key == "communications_coordination":
        _require("Airspace class", _has_text(getattr(planning, "airspace_class", "")))
        _require(
            "Nearest airport",
            _has_text(getattr(planning, "nearest_airport", "")) or bool(getattr(planning, "nearest_airport_ref_id", None)),
        )
        _require("Distance to airport (NM)", getattr(planning, "distance_to_airport_nm", None) is not None)

        airport = getattr(planning, "nearest_airport_ref", None)
        if airport is not None and hasattr(airport, "artcc_name") and hasattr(airport, "artcc_id"):
            _require("ARTCC name (recommended)", _has_text(getattr(airport, "artcc_name", "")))
            _require("ARTCC ID (recommended)", _has_text(getattr(airport, "artcc_id", "")))

    elif key == "safety_systems_risk_mitigation":
        _require("Safety features notes", _has_text(getattr(planning, "safety_features_notes", "")))
        _require("Prepared procedures (select at least one)", bool(getattr(planning, "prepared_procedures", None)))

    elif key == "operational_limitations":
        _require("Max altitude AGL", getattr(planning, "proposed_agl", None) is not None)
        _require("Airspace class", _has_text(getattr(planning, "airspace_class", "")))
        _require("Timeframe (select at least one)", bool(getattr(planning, "timeframe", None)))

    elif key == "emergency_contingency":
        _require("Prepared procedures (select at least one)", bool(getattr(planning, "prepared_procedures", None)))

    elif key == "compliance_statement":
        if getattr(planning, "operates_under_10739", False):
            _require(
                "107.39 waiver number or waiver document",
                bool(getattr(planning, "oop_waiver_number", None)) or bool(getattr(planning, "oop_waiver_document_id", None)),
            )
        if getattr(planning, "operates_under_107145", False):
            _require(
                "107.145 waiver number or waiver document",
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
    section.save(update_fields=["content", "generated_at", "updated_at"])

    validate_conops_section(section)
    return result


def planning_aircraft_summary(planning) -> dict:
    """
    Returns normalized aircraft strings for narrative sections.
    """
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
