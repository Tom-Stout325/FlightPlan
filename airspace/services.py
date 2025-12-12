# airspace/services.py

from __future__ import annotations

from typing import Optional, List, Dict, Any

from django.conf import settings
from django.utils import timezone

from openai import OpenAI

from .constants import CONOPS_SECTIONS
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
    return f"""
You are writing a professional FAA Concept of Operations (CONOPS) section.

SECTION: {section.title}

RULES:
- Write in formal FAA language.
- No bullets unless appropriate.
- Use only data provided by the planning record.
- This section must stand alone.

OPERATION TITLE: {_clean(planning.operation_title)}
VENUE: {_clean(planning.venue_name)}
AIRSPACE: {_clean(planning.airspace_class)}
AIRCRAFT: {_clean(planning.aircraft_display())}
RPIC: {_clean(planning.pilot_display_name())}

WRITE THE CONTENT FOR THIS SECTION ONLY.
""".strip()


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
    section.save(update_fields=["content", "generated_at"])

    validate_conops_section(section)
    return result


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
    "communications_coordination": 60,
    "safety_systems_risk_mitigation": 80,
    "operational_limitations": 40,
    "emergency_contingency": 80,
    "compliance_statement": 40,
    "appendices": 10,
}


def validate_conops_section(section) -> None:
    text = (section.content or "").strip()
    min_words = MIN_WORDS_BY_SECTION.get(section.section_key, 50)
    word_count = len(text.split())

    section.is_complete = bool(text and word_count >= min_words)
    section.validated_at = timezone.now()
    section.save(update_fields=["is_complete", "validated_at"])
