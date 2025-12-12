# airspace/services.py

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Dict, Any
from django.conf import settings
from openai import OpenAI

# Imports for choices
from .forms import (
    TIMEFRAME_CHOICES,
    PURPOSE_OPERATIONS_CHOICES,
    GROUND_ENVIRONMENT_CHOICES,
    PREPARED_PROCEDURES_CHOICES,
)
from .constants import CONOPS_SECTIONS

if TYPE_CHECKING:
    from .models import WaiverPlanning


from django.utils import timezone







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





# ------------------------------------------------------------------
# Small internal helpers (used only in this file)
# ------------------------------------------------------------------


def _to_list(v):
    """
    Normalize a value into a list of strings.

    Handles:
    - None
    - list (ArrayField)
    - comma-separated string (CSV)
    """
    if not v:
        return []
    if isinstance(v, list):
        return [x for x in v if x]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def _labels(values: List[str], choices: List[tuple]) -> List[str]:
    mapping = dict(choices)
    return [mapping.get(v, v) for v in values if v]

def get_openai_client() -> OpenAI:
    """
    Return a configured OpenAI client.

    Raises a clear error if the API key is missing so you don't
    get mysterious 401s in production.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set in settings / environment. "
            "Add it to your .env and settings before calling OpenAI."
        )
    return OpenAI(api_key=api_key)








def _labels_from_choices(values: List[str], choices: List[tuple]) -> List[str]:
    """Convert stored keys (ArrayField codes) into display labels."""
    if not values:
        return []
    mapping = dict(choices)
    return [mapping.get(v, v) for v in values if v]


def _clean(s: Optional[str]) -> str:
    return (s or "").strip()


def _bool_text(v: bool) -> str:
    return "Yes" if bool(v) else "No"




def build_waiver_description_prompt(planning: WaiverPlanning) -> str:
    """
    Build a strict prompt for a SHORT 'Description of Operations' (not a CONOPS).
    Uses ONLY provided planning fields and avoids hallucinations.
    """

    # Convert stored codes -> labels for readability
    timeframe_labels = _labels_from_choices(planning.timeframe_codes(), TIMEFRAME_CHOICES)
    purpose_labels = _labels_from_choices(planning.purpose_operations or [], PURPOSE_OPERATIONS_CHOICES)
    ground_labels = _labels_from_choices(planning.ground_environment or [], GROUND_ENVIRONMENT_CHOICES)
    procedure_labels = _labels_from_choices(planning.prepared_procedures or [], PREPARED_PROCEDURES_CHOICES)

    # Pilot + aircraft using your helpers
    pilot_name = _clean(planning.pilot_display_name())
    pilot_cert = _clean(planning.pilot_cert_display())
    pilot_hours = planning.pilot_flight_hours

    aircraft = _clean(planning.aircraft_display())
    aircraft_count = planning.aircraft_count

    # Address one-liner (omit blanks)
    addr_bits = [
        _clean(planning.street_address),
        _clean(planning.location_city),
        _clean(planning.location_state),
        _clean(planning.zip_code),
    ]
    address = ", ".join([b for b in addr_bits if b])

    # Optional / short context fields (these exist on WaiverPlanning)
    date_range = ""
    if planning.start_date and planning.end_date and planning.start_date != planning.end_date:
        date_range = f"{planning.start_date} to {planning.end_date}"
    elif planning.start_date:
        date_range = f"{planning.start_date}"

    # Keep it short: we provide “facts” only.
    data: Dict[str, Any] = {
        "Operation Title": _clean(planning.operation_title),
        "Venue Name": _clean(planning.venue_name),
        "Venue Address": address,
        "Launch Location / Staging": _clean(planning.launch_location),

        "Purpose (selected)": ", ".join(purpose_labels),
        "Purpose details": _clean(planning.purpose_operations_details),

        "Dates": date_range,
        "Timeframes": ", ".join(timeframe_labels),
        "Frequency": _clean(planning.frequency),
        "Local Time Zone": _clean(planning.local_time_zone),

        "Airspace Class": _clean(planning.airspace_class),
        "Nearest Airport": _clean(planning.nearest_airport),
        "Operating Radius": _clean(planning.location_radius),
        "Planned Max Altitude AGL (ft)": planning.proposed_agl or "",

        "Aircraft": aircraft,
        "Aircraft count": aircraft_count or "",
        "RPIC name": pilot_name,
        "RPIC certificate #": pilot_cert,
        "Approx. RPIC UAS hours": f"{pilot_hours}" if pilot_hours is not None else "",

        "Visual Observer used": _bool_text(planning.has_visual_observer),
        "Drone detection used": _bool_text(planning.uses_drone_detection),
        "Flight tracking used": _bool_text(planning.uses_flight_tracking),

        "Safety notes": _clean(planning.safety_features_notes),

        "Ground environment": ", ".join(ground_labels),
        "Estimated crowd size": _clean(planning.estimated_crowd_size),
        "Prepared procedures": ", ".join(procedure_labels),

        "Operating under §107.39 (OOP) waiver": _bool_text(planning.operates_under_10739),
        "§107.39 waiver number": _clean(planning.oop_waiver_number),
        "Operating under §107.145 (moving vehicles) waiver": _bool_text(planning.operates_under_107145),
        "§107.145 waiver number": _clean(planning.mv_waiver_number),
    }

    # Soft “missing” note (to discourage invention)
    missing = [k for k, v in data.items() if v in ("", None)]
    missing_note = "None." if not missing else ", ".join(missing)

    return f"""
You are helping write a SHORT “Description of Operations” for an FAA DroneZone Part 107 airspace waiver/authorization submission.

HARD REQUIREMENTS (must follow exactly):
- Output MUST be exactly 2 short paragraphs, no headings.
- Each paragraph must be 2–4 sentences. Total length 120–200 words.
- NO bullets, NO lists, NO “Quick Facts”, NO colons-as-headings, NO markdown.
- This is NOT a CONOPS. Do NOT include detailed procedures, checklists, or emergency step-by-step.
- Use ONLY the facts provided in DATA. If a value is missing, omit that detail—do not guess or invent.
- Do not add new dates, airports, airspace classes, equipment capabilities, crowd sizes, names, certificate numbers, or flight hours unless explicitly present in DATA.
- If the operation is NOT under §107.39 or §107.145, state that clearly in one sentence.

MISSING/INCOMPLETE FIELDS (for awareness only; do not invent): {missing_note}

DATA (authoritative):
{data}

WRITE:
Paragraph 1: What / where / when / overall flight profile in one tight narrative.
Paragraph 2: Safety posture (VO use, situational awareness tools if listed, basic controls) + waiver dependency statement.
""".strip()


def generate_waiver_description_text(planning, *, model="gpt-5-mini") -> str:
    client = get_openai_client()
    prompt_text = build_waiver_description_prompt(planning)

    response = client.responses.create(
        model=model,
        input=prompt_text,
        max_output_tokens=1200,
        text={"format": {"type": "text"}},
    )

    result = (response.output_text or "").strip()
    if not result:
        raise RuntimeError("OpenAI response.output_text was empty.")
    return result



from django.utils import timezone
from .models import ConopsSection



def ensure_conops_sections(application):
    """
    Ensure all CONOPS sections exist for a waiver application.
    Safe to call multiple times.
    """
    existing = set(
        application.conops_sections.values_list("section_key", flat=True)
    )

    new_sections = []
    for key, title in CONOPS_SECTIONS:
        if key not in existing:
            new_sections.append(
                ConopsSection(
                    application=application,
                    section_key=key,
                    title=title,
                )
            )

    if new_sections:
        ConopsSection.objects.bulk_create(new_sections)
        
        
# ==========================================================
#              CONOPS GENERATION
# ==========================================================

def build_conops_section_prompt(*, application, planning, section):
    ...



def generate_conops_section_text(*, application, section, model=None) -> str:
    ...


def validate_conops_section(section):
    text = (section.content or "").strip()
    min_words = MIN_WORDS_BY_SECTION.get(section.section_key, 50)
    word_count = len(text.split())

    section.is_complete = bool(text and word_count >= min_words)
    section.validated_at = timezone.now()
    section.save(update_fields=["is_complete", "validated_at"])