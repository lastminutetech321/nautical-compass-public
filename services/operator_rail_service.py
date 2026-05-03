"""
Operator Rail Service — builds and scores an operator compliance profile
from intake form data. Called by intake_engine when intake_type == "partner".
"""

OPERATOR_TYPE_MAP = {
    "av_production":    "AV Production / Crew Services",
    "labor_provider":   "Labor Provider / Staffing",
    "event_production": "Event Production Company",
    "venue_operator":   "Venue Operator",
    "other_operator":   "Other Operator Type",
}

ENTITY_TYPE_MAP = {
    "llc":         "LLC",
    "sole_prop":   "Sole Proprietorship",
    "s_corp":      "S Corporation",
    "c_corp":      "C Corporation",
    "partnership": "Partnership",
    "dba":         "DBA / Trade Name",
}

EIN_STATUS_MAP = {
    "on_file":     "EIN on file",
    "applied":     "Applied — pending",
    "not_started": "Not started",
}

W9_STATUS_MAP = {
    "complete":    "W-9 complete",
    "in_progress": "In progress",
    "not_ready":   "Not ready",
}

INSURANCE_STATUS_MAP = {
    "active":      "General liability — active",
    "pending":     "Pending / in process",
    "not_covered": "Not covered",
}

_COMPLIANCE_FIELDS = [
    ("entity_type",        "Entity type"),
    ("operator_type_rail", "Operator service type"),
    ("service_area",       "Primary service area"),
    ("formation_state",    "State of formation"),
    ("ein_status",         "EIN status"),
    ("w9_status",          "W-9 status"),
    ("insurance_status",   "Insurance status"),
]


def _next_steps(fields: dict) -> list:
    steps = []
    if not fields.get("entity_type"):
        steps.append("Select entity type to begin compliance mapping")
    if not fields.get("operator_type_rail"):
        steps.append("Select operator service type for routing")
    if not fields.get("formation_state"):
        steps.append("Provide state of formation for entity verification")
    ein = fields.get("ein_status", "")
    if not ein or ein == "not_started":
        steps.append("Obtain EIN from IRS (Form SS-4)")
    w9 = fields.get("w9_status", "")
    if not w9 or w9 == "not_ready":
        steps.append("Complete W-9 form for tax documentation on file")
    ins = fields.get("insurance_status", "")
    if not ins or ins == "not_covered":
        steps.append("Obtain general liability insurance certificate of coverage")
    if not steps:
        steps.append("All core compliance fields complete — proceed to operator verification")
    return steps


def build_operator_profile(data: dict) -> dict:
    """Return an operator rail profile dict derived from intake form data."""
    fields = {k: (data.get(k) or "").strip() for k, _ in _COMPLIANCE_FIELDS}

    present = [k for k, v in fields.items() if v]
    readiness_score = round(len(present) / len(_COMPLIANCE_FIELDS) * 100)
    missing_compliance = [label for k, label in _COMPLIANCE_FIELDS if not fields[k]]

    return {
        "entity_type":            fields["entity_type"],
        "entity_type_label":      ENTITY_TYPE_MAP.get(fields["entity_type"], fields["entity_type"]),
        "operator_type":          fields["operator_type_rail"],
        "operator_type_label":    OPERATOR_TYPE_MAP.get(fields["operator_type_rail"], fields["operator_type_rail"]),
        "service_area":           fields["service_area"],
        "formation_state":        fields["formation_state"],
        "ein_status":             fields["ein_status"],
        "ein_status_label":       EIN_STATUS_MAP.get(fields["ein_status"], fields["ein_status"]),
        "w9_status":              fields["w9_status"],
        "w9_status_label":        W9_STATUS_MAP.get(fields["w9_status"], fields["w9_status"]),
        "insurance_status":       fields["insurance_status"],
        "insurance_status_label": INSURANCE_STATUS_MAP.get(fields["insurance_status"], fields["insurance_status"]),
        "readiness_score":        readiness_score,
        "missing_compliance":     missing_compliance,
        "compliance_complete":    len(missing_compliance) == 0,
        "next_steps":             _next_steps(fields),
    }
