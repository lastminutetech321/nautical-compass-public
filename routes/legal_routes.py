from fastapi import APIRouter, Request, HTTPException
from typing import Any, Dict

from services.standing_engine import (
    analyze_injury,
    analyze_causation,
    analyze_redressability,
    analyze_capacity,
    build_claims,
)

router = APIRouter()

REQUIRED_FIELDS = [
    "actor_type",
    "harm_type",
    "harm_description",
    "defendant_type",
    "requested_relief",
]


@router.post("/api/legal/standing/analyze")
def standing_analyze(data: Dict[str, Any]):
    for field in REQUIRED_FIELDS:
        if not (data.get(field) or "").strip():
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    injury = analyze_injury(data)
    causation = analyze_causation(data)
    redress = analyze_redressability(data)
    capacity = analyze_capacity(data)
    claims = build_claims(data)

    standing = {
        "injury_in_fact": injury["injury_exists"],
        "causation": causation["causation_established"],
        "redressability": redress["redressability_met"],
        "passes_lujan": (
            injury["injury_exists"]
            and causation["causation_established"]
            and redress["redressability_met"]
        ),
    }

    capacity_block = {
        "recommended": capacity["capacity_type"],
        "notes": capacity["applicable_doctrines"],
    }

    return {
        "standing": standing,
        "capacity": capacity_block,
        "claims": claims,
        "relief": {
            "requested": data.get("requested_relief"),
        },
    }
