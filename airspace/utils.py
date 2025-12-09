from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional


# ---------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------


def dms_to_decimal(
    degrees: int | float | Decimal,
    minutes: int | float | Decimal,
    seconds: int | float | Decimal,
    direction: str,
) -> Decimal:
    """
    Convert Degrees / Minutes / Seconds + direction (N/S/E/W) to decimal degrees.

    N / E => positive
    S / W => negative
    """
    deg = Decimal(str(degrees))
    mins = Decimal(str(minutes))
    secs = Decimal(str(seconds))

    decimal = deg + (mins / Decimal("60")) + (secs / Decimal("3600"))

    direction = (direction or "").upper()
    if direction in ("S", "W"):
        decimal = -decimal

    return decimal


# ---------------------------------------------------------------------
# Short Description generator
# ---------------------------------------------------------------------


def _clean_snippet(text: Optional[str], max_len: int = 140) -> Optional[str]:
    """
    Collapse whitespace into single spaces and truncate to max_len characters.
    Returns None for empty/whitespace-only input.
    """
    if not text:
        return None

    # Collapse newlines and multiple spaces
    snippet = " ".join(str(text).split())

    if not snippet:
        return None

    if len(snippet) > max_len:
        return snippet[: max_len - 1].rstrip() + "…"

    return snippet


def generate_short_description(waiver: Any) -> str:
    """
    Build an ultra-brief FAA-style 'Brief Description of Operations'
    from an AirspaceWaiver instance.

    Baseline structure (your approved copy):

      "The RPIC will conduct sUAS flights for aerial imaging within the
       defined area, remaining below the requested maximum AGL and
       launching from a secure location. Operations will follow VLOS
       requirements, use a qualified VO as needed, and employ a
       GPS-stabilized aircraft with safety features. The RPIC will
       perform standard pre-flight checks, monitor the area for hazards,
       and cease operations if unsafe conditions arise."
    """

    # ------------------------------------------------------------------
    # Purpose / operation type
    # ------------------------------------------------------------------
    purpose = "aerial imaging"

    # If you later enrich operation_activities, this will automatically
    # reflect that without breaking.
    activities_raw = getattr(waiver, "operation_activities", None)

    if activities_raw:
        if isinstance(activities_raw, (list, tuple, set)):
            codes = [str(c).strip() for c in activities_raw if str(c).strip()]
        else:
            # Treat as comma-separated string or single value
            codes = [
                c.strip()
                for c in str(activities_raw).split(",")
                if c.strip()
            ]

        if codes:
            # You can later map codes -> human phrases; for now we just
            # indicate that more than simple imaging is involved.
            purpose = "aerial imaging and related UAS operations"

    # ------------------------------------------------------------------
    # Location snippet (proposed_location)
    # ------------------------------------------------------------------
    location_snippet = _clean_snippet(getattr(waiver, "proposed_location", ""))

    # ------------------------------------------------------------------
    # Maximum AGL
    # ------------------------------------------------------------------
    max_agl: Optional[int] = None
    try:
        max_agl_value = getattr(waiver, "max_agl", None)
        if max_agl_value is not None:
            max_agl = int(max_agl_value)
    except (TypeError, ValueError):
        max_agl = None

    # ------------------------------------------------------------------
    # Sentence 1 – core mission
    # ------------------------------------------------------------------
    if location_snippet and max_agl is not None:
        first_sentence = (
            f"The RPIC will conduct sUAS flights for {purpose} within the defined area near "
            f"{location_snippet}, remaining below approximately {max_agl} feet AGL and "
            f"launching from a secure location."
        )
    elif max_agl is not None:
        first_sentence = (
            f"The RPIC will conduct sUAS flights for {purpose} within the defined area, "
            f"remaining below approximately {max_agl} feet AGL and launching from a "
            f"secure location."
        )
    else:
        first_sentence = (
            f"The RPIC will conduct sUAS flights for {purpose} within the defined area, "
            f"and will maintain an altitude at or below AGL and launching from a controlled "
            f"location."
        )

    # ------------------------------------------------------------------
    # Sentence 2 – VLOS / VO / safety language
    # ------------------------------------------------------------------
    second_sentence = (
        "Operations will follow VLOS requirements, utilize a qualified VO, and employ "
        "a GPS-stabilized aircraft with manufacturers safety features. The RPIC will perform standard "
        "pre-flight checks, monitor the area for hazards, and cease operations if unsafe "
        "conditions arise."
    )

    # Ensure a clean space between sentences
    return f"{first_sentence} {second_sentence}"
