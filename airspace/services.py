from __future__ import annotations

from django.conf import settings
from openai import OpenAI
from typing import List



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




def build_conops_prompt(waiver: AirspaceWaiver) -> str:
    """
    Build a highly structured FAA-style CONOPS prompt with:
    - FAA waiver guidance phrasing
    - Clear outline matching FAA expectations
    - Soft validation of missing waiver fields
    - Integration of planning data (aircraft, pilot, launch, safety)
    """

    # Detect missing critical waiver fields (soft hints for the model)
    missing = []
    FIELD_MAP = {
        "operation_title": "Operation Title",
        "proposed_location": "Proposed Location",
        "max_agl": "Maximum Altitude (AGL)",
        "lat_decimal": "Latitude",
        "lon_decimal": "Longitude",
        "nearest_airport": "Nearest Airport (ICAO)",
        "airspace_class": "Airspace Class",
        "description": "Description of Proposed Operations",
    }
    for field, label in FIELD_MAP.items():
        value = getattr(waiver, field, None)
        if value in (None, "", 0):
            missing.append(label)

    missing_note = (
        "None – all primary fields appear populated."
        if not missing
        else "The following fields appear to be missing or incomplete: "
        + ", ".join(missing)
        + "."
    )

    timeframe = dict(waiver.TIMEFRAME_CHOICES).get(waiver.timeframe, "")
    frequency = dict(waiver.FREQUENCY_CHOICES).get(waiver.frequency, "")

    # ---- Planning data (may or may not exist) ----
    planning = getattr(waiver, "planning", None)

    pilot_name = ""
    pilot_cert = ""
    pilot_hours_text = ""
    aircraft_text = ""
    extra_aircraft = ""
    launch_location = ""
    safety_notes = ""

    if planning:
        pilot_name = planning.pilot_display_name()
        pilot_cert = planning.pilot_cert_display()
        if planning.pilot_flight_hours is not None:
            pilot_hours_text = f"{planning.pilot_flight_hours} hours (approximate)"
        aircraft_text = planning.aircraft_display()
        extra_aircraft = planning.aircraft_manual or ""
        launch_location = planning.launch_location or ""
        safety_notes = planning.safety_features_notes or ""

    if not pilot_name:
        pilot_name = "[Pilot name not specified]"
    if not pilot_cert:
        pilot_cert = "[Certificate number not specified]"
    if not pilot_hours_text:
        pilot_hours_text = "[Total UAS flight hours not specified]"
    if not aircraft_text:
        aircraft_text = "[Aircraft details not specified; see waiver aircraft description]"
    if not launch_location:
        launch_location = "[Launch location not specified]"
    if not safety_notes:
        safety_notes = "[Safety features not specified; rely on standard mitigations and onboard safeguards]"

    # Visual Observer – always state that a VO will be used, even if identity is unknown.
    visual_observer_text = (
        "A visual observer (VO) will be used to maintain visual line of sight, "
        "assist with air and ground risk scanning, and support safe operations in accordance "
        "with 14 CFR § 107.33. Individual VO identities may vary by event and are not fixed "
        "at the time of application.  All VOs will undergo internal training prior to operations."
    )

    return f"""
You are an FAA Part 107 waiver and airspace specialist. 
Write a complete, FAA-style Concept of Operations (CONOPS) suitable for inclusion in an FAA DroneZone waiver application. 
Follow the FAA's Waiver Safety Explanation Guideline (WSEG) structure and safety-focused expectations.

Your CONOPS must:

- Use clear, formal aviation language appropriate for the FAA.
- Follow FAA operational-risk-based structure.
- Avoid inventing any details not provided. If required data is missing, say: "[Missing Information]".
- Be written in short, well-structured paragraphs — no bullets in final output.
- Present mitigations, procedures, and safety rationales consistent with FAA advisory circulars.

---------------------------------------------------------------------
### Missing or incomplete waiver fields:
{missing_note}
---------------------------------------------------------------------

### FAA-Required CONOPS Structure  
Use all sections below, modeled closely after FAA guidance:

**1. Overview of the Proposed Operation**  
State the purpose, type of operation, aircraft category, and why this operation requires FAA review.

**2. Operating Environment & Airspace**  
Describe the geographical area, environment, airspace classification, obstacles, nearby airports, and operational radius.

**3. Command, Control & Communications**  
Explain control links, frequencies, link robustness, lost-link behavior, and how command authority is maintained.

**4. Crew Qualifications & Responsibilities**  
Describe the Remote Pilot in Command, visual observer(s), and any additional crew, including responsibilities and communications.
Be explicit that a visual observer will be used consistent with § 107.33, even if specific VO identities are not yet determined.

**5. Normal Operating Procedures**  
Describe preflight, launch, climb, cruise, descent, and landing procedures, including checklists and communications.

**6. Abnormal & Emergency Procedures**  
Detail how you handle lost link, flyaways, incursions by non-participating aircraft or people, loss of GPS, or system failures.

**7. Ground & Air Risk Assessment**  
Describe how you identify, assess, and mitigate both air and ground risks, including crowd proximity and overflight controls.

**8. Safety Features & Risk Mitigations**  
Summarize onboard and procedural mitigations:
- Aircraft safety features  
- Operational mitigations  
- Crew mitigations  
- Equipment mitigations  

**9. Compliance with 14 CFR Part 107 & Waiver Conditions**  
Explain how the operator ensures compliance with Part 107 and any waiver-specific conditions.

---------------------------------------------------------------------
### Waiver Data Provided by Operator

Operation Title: {waiver.operation_title or "[Missing Information]"}

Dates of Operation: {waiver.start_date} to {waiver.end_date}  
Timeframe: {timeframe or "[Missing]"}  
# Frequency: {frequency or "[Missing]"}  
Local Time Zone: {waiver.local_timezone or "[Missing]"}  

Airspace Class: {waiver.get_airspace_class_display() if hasattr(waiver, "get_airspace_class_display") else waiver.airspace_class}  
Maximum Altitude (AGL): {waiver.max_agl} ft  
Radius (NM): {waiver.radius_nm}  

Proposed Location: {waiver.proposed_location or "[Missing]"}  
Nearest Airport (ICAO): {waiver.nearest_airport or "[Missing]"}  

Latitude (decimal): {waiver.lat_decimal}  
Longitude (decimal): {waiver.lon_decimal}  



---------------------------------------------------------------------
### Crew & Equipment Details from Planning (Optional)

Remote Pilot in Command (Name): {pilot_name}  
Remote Pilot Certificate Number: {pilot_cert}  
Approximate UAS Flight Hours: {pilot_hours_text}

Primary Aircraft (from Equipment / planning): {aircraft_text}  
Additional / Manual Aircraft Notes: {extra_aircraft or "[None specified]"}

Launch Location / Staging Description: {launch_location}

Visual Observer Usage:  
{visual_observer_text}

Safety Features & Mitigations (from planning):  
{safety_notes}

---------------------------------------------------------------------
Using the structure above and only the information provided, write the full CONOPS in narrative paragraph form (no bullet lists) suitable for direct submission to the FAA.
"""



def generate_conops_text(waiver: AirspaceWaiver, *, model: str = "gpt-5-mini") -> str:
    """
    Call OpenAI to generate a CONOPS text for the given waiver.

    Returns the plain text body. Caller is responsible for saving it.
    """
    client = get_openai_client()
    prompt_text = build_conops_prompt(waiver)

    response = client.responses.create(
        model=model,
        input=prompt_text,
        max_output_tokens=6000,
        # NOTE: 'temperature' is not supported for this model with Responses API,
        # so we omit it to avoid 400 BadRequestError.
    )

    return response.output_text









def generate_short_description(waiver) -> str:
    """
    Build an FAA-friendly short description of the proposed operation
    using structured fields from the AirspaceWaiver instance.

    Intended to populate waiver.short_description (Step 3) as an editable default.
    """

    def list_to_english(items: List[str]) -> str:
        """Turn ['A', 'B', 'C'] into 'A, B, and C'."""
        items = [i for i in items if i]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return f"{', '.join(items[:-1])}, and {items[-1]}"

    # --- What are you doing? (activities) ---
    activity_labels = []
    if hasattr(waiver, "operation_activity_labels"):
        activity_labels = waiver.operation_activity_labels()

    if activity_labels:
        activity_phrase = list_to_english([a.lower() for a in activity_labels])
    else:
        activity_phrase = "small unmanned aircraft system (sUAS) operations"

    extra_details = getattr(waiver, "operation_activities_other", "") or ""
    extra_details = extra_details.strip()
    if extra_details:
        # e.g. "event filming and aerial photography (live broadcast coverage of NHRA national events ...)"
        activity_phrase = f"{activity_phrase} ({extra_details})"

    # --- When (dates, frequency, timeframe) ---
    start_date = getattr(waiver, "start_date", None)
    end_date = getattr(waiver, "end_date", None)

    if start_date and end_date:
        if start_date == end_date:
            date_phrase = f"on {start_date:%b} {start_date.day}, {start_date.year}"
        else:
            date_phrase = (
                f"from {start_date:%b} {start_date.day}, {start_date.year} "
                f"through {end_date:%b} {end_date.day}, {end_date.year}"
            )
    elif start_date:
        date_phrase = f"starting on {start_date:%b} {start_date.day}, {start_date.year}"
    else:
        date_phrase = "on the specified dates"

    # Frequency (Daily, Weekly, etc.)
    try:
        frequency_display = waiver.get_frequency_display()
    except Exception:
        frequency_display = ""

    freq_phrase = (
        f"on a {frequency_display.lower()} basis" if frequency_display else "as scheduled"
    )

    # Timeframe (Sunrise–Noon, etc.) – handles CSV from the checkbox field
    tf_map = {}
    if hasattr(waiver, "TIMEFRAME_CHOICES"):
        tf_map = dict(waiver.TIMEFRAME_CHOICES)

    timeframe_raw = getattr(waiver, "timeframe", "") or ""
    timeframe_codes = [
        c.strip() for c in timeframe_raw.split(",") if c.strip()
    ]
    timeframe_labels = [tf_map.get(code, code) for code in timeframe_codes]

    if timeframe_labels:
        timeframe_phrase = f"during {list_to_english(timeframe_labels)}"
    else:
        timeframe_phrase = "during the specified time windows"

    # --- Where (location, radius, airspace) ---
    proposed_location = (getattr(waiver, "proposed_location", "") or "").strip()

    radius_nm = getattr(waiver, "radius_nm", None)
    radius_phrase = ""
    if radius_nm:
        radius_phrase = f"within approximately {radius_nm} NM"

    nearest_airport = (getattr(waiver, "nearest_airport", "") or "").strip()

    try:
        airspace_display = waiver.get_airspace_class_display()
    except Exception:
        airspace_display = ""

    location_bits = []

    if proposed_location:
        location_bits.append(f"in the vicinity of {proposed_location}")

    if radius_phrase and nearest_airport:
        location_bits.append(f"{radius_phrase} of {nearest_airport}")
    elif nearest_airport:
        location_bits.append(f"in the vicinity of {nearest_airport}")
    elif radius_phrase:
        location_bits.append(radius_phrase)

    if airspace_display:
        location_bits.append(f"in {airspace_display} airspace")

    if location_bits:
        location_phrase = ", ".join(location_bits)
    else:
        location_phrase = "in the proposed operating area"

    # --- How high / aircraft ---
    max_agl = getattr(waiver, "max_agl", None)
    altitude_phrase = (
        f"at or below {max_agl} feet AGL" if max_agl else "at the requested altitudes"
    )

    # Aircraft name
    aircraft_name = ""
    aircraft = getattr(waiver, "aircraft", None)
    if aircraft is not None:
        # adjust attribute as needed; using full_display_name from your Equipment model
        aircraft_name = getattr(aircraft, "full_display_name", "").strip()

    if not aircraft_name:
        aircraft_name = (getattr(waiver, "aircraft_custom", "") or "").strip()

    if aircraft_name:
        aircraft_phrase = f"using a {aircraft_name}"
    else:
        aircraft_phrase = "using a small UAS (sUAS)"

    # --- Build the core sentence ---
    # Example result:
    # "Part 107 operation to conduct event filming and aerial photography (live broadcast coverage...)
    #  using a DJI Avata 2, in the vicinity of zMAX Dragway, within approximately 0.50 NM of KJQF in Class D airspace,
    #  from Mar 20, 2026 through Mar 22, 2026, during Sunrise to Noon and 4 PM to Sunset,
    #  at or below 150 feet AGL on a daily basis."
    parts = [
        "Part 107 operation to conduct",
        activity_phrase,
        aircraft_phrase,
        location_phrase + ",",
        date_phrase + ",",
        timeframe_phrase + ",",
        altitude_phrase,
        f"{freq_phrase}.",
    ]

    # Clean up spaces and punctuation
    sentence = " ".join(p for p in parts if p).replace(" ,", ",")

    # --- Optional: mention existing 107.39 waiver if present on the model ---
    uses_oop = getattr(waiver, "uses_107_39_waiver", False)
    oop_number = (getattr(waiver, "oop_waiver_number", "") or "").strip()

    if uses_oop:
        if oop_number:
            sentence += (
                f" Operations will be conducted in accordance with existing 14 CFR §107.39 "
                f"Operations Over People waiver #{oop_number} and its associated mitigations."
            )
        else:
            sentence += (
                " Operations will be conducted in accordance with an existing 14 CFR §107.39 "
                "Operations Over People waiver and its associated mitigations."
            )

    return sentence
