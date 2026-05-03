"""
Labor Rail Service — builds and scores a crew readiness profile
from intake form data. Called by intake_engine when intake_type
is "labor" or "production".
"""

ROLE_TYPE_MAP = {
    "av_technician":      "AV Technician",
    "lighting_technician": "Lighting Technician",
    "audio_engineer":     "Audio Engineer",
    "video_engineer":     "Video Engineer",
    "rigger":             "Rigger",
    "stage_manager":      "Stage Manager / Coordinator",
    "crew_lead":          "Crew Lead / Foreman",
    "labor_general":      "General Labor",
    "other_crew":         "Other Crew Role",
}

AVAILABILITY_MAP = {
    "immediately":    "Available immediately",
    "within_1_week":  "Available within 1 week",
    "within_2_weeks": "Available within 2 weeks",
    "specific_dates": "Specific dates only",
}

UNION_STATUS_MAP = {
    "iatse":      "IATSE member",
    "ibew":       "IBEW member",
    "non_union":  "Non-union",
    "open":       "Open to either",
}

_READINESS_FIELDS = [
    ("role_type",       "Role / trade"),
    ("availability",    "Availability"),
    ("labor_location",  "Location / service area"),
    ("rate_expectation","Rate expectation"),
    ("skills",          "Skills or certifications"),
]


def _next_steps(fields: dict) -> list:
    steps = []
    if not fields.get("role_type"):
        steps.append("Select your role or trade to begin crew matching")
    if not fields.get("availability"):
        steps.append("Confirm your availability so dispatch can route your intake")
    if not fields.get("labor_location"):
        steps.append("Provide your location or service area for local dispatch matching")
    if not fields.get("rate_expectation"):
        steps.append("State your rate expectation (day rate or hourly) to confirm fit")
    if not fields.get("skills"):
        steps.append("List key skills or certifications to improve match quality")
    if not steps:
        steps.append("Crew profile complete — intake is ready for dispatch review")
    return steps


def build_labor_profile(data: dict) -> dict:
    """Return a labor rail profile dict derived from intake form data."""
    fields = {k: (data.get(k) or "").strip() for k, _ in _READINESS_FIELDS}
    labor_evidence = [v for v in (data.get("labor_evidence") or []) if v]
    union_status = (data.get("union_status") or "").strip()

    present = [k for k, v in fields.items() if v]
    readiness_score = round(len(present) / len(_READINESS_FIELDS) * 100)
    missing_readiness = [label for k, label in _READINESS_FIELDS if not fields[k]]

    return {
        "role_type":            fields["role_type"],
        "role_type_label":      ROLE_TYPE_MAP.get(fields["role_type"], fields["role_type"]),
        "availability":         fields["availability"],
        "availability_label":   AVAILABILITY_MAP.get(fields["availability"], fields["availability"]),
        "labor_location":       fields["labor_location"],
        "rate_expectation":     fields["rate_expectation"],
        "skills":               fields["skills"],
        "union_status":         union_status,
        "union_status_label":   UNION_STATUS_MAP.get(union_status, union_status),
        "labor_evidence":       labor_evidence,
        "readiness_score":      readiness_score,
        "missing_readiness":    missing_readiness,
        "crew_ready":           readiness_score >= 80,
        "next_steps":           _next_steps(fields),
    }
