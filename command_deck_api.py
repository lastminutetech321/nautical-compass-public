"""
Nautical Compass — Command Deck Data API (FastAPI)
# Command Deck Data API (FastAPI)
Provides JSON endpoints for the Command Deck frontend:
  - /api/command-deck/status  — system state metrics
  - /api/command-deck/weather — weather conditions (mock or live)

Usage in main.py:
    from command_deck_api import router as command_deck_api_router
    app.include_router(command_deck_api_router)

Environment Variables:
    WEATHER_API_KEY  — If set, attempts to fetch live weather from OpenWeatherMap.
                       Falls back to mock data on failure or if unset.
"""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/command-deck", tags=["command-deck-api"])

# ---------------------------------------------------------------------------
# /api/command-deck/status
# ---------------------------------------------------------------------------

MOCK_STATUS = {
    "standing": 85,
    "capacity": 72,
    "jurisdiction": 90,
    "evidence": 68,
    "compliance": 94,
    "deployment": 77,
    "system_health": "operational",
    "active_cases": 15,
}

_STANDING_SCORES = {
    "standing_established":                      92,
    "standing_likely_with_remedy_clarification": 74,
    "standing_needs_causation_and_remedy":        48,
    "standing_not_established":                   22,
}


@router.get("/status")
def command_deck_status():
    """Return current system state metrics for the Command Deck dials."""
    data = dict(MOCK_STATUS)
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return JSONResponse(content=data)


# ---------------------------------------------------------------------------
# /api/command-deck/weather
# ---------------------------------------------------------------------------

MOCK_WEATHER = {
    "condition": "clear",
    "temperature": 72,
    "wind_speed": 12,
    "wind_direction": "NE",
    "humidity": 45,
    "visibility": 10,
    "source": "mock",
}


def _fetch_live_weather(lat: float, lon: float) -> dict | None:
    """
    Attempt to fetch live weather from OpenWeatherMap for given coordinates.
    Returns a normalized dict on success, or None on failure.
    """
    api_key = os.getenv("WEATHER_API_KEY", "").strip()
    if not api_key:
        return None

    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
    )

    try:
        import urllib.request
        import json

        with urllib.request.urlopen(url, timeout=5) as resp:
            raw = json.loads(resp.read().decode())

        # Map wind degrees to compass direction
        deg = raw.get("wind", {}).get("deg", 0)
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        wind_dir = directions[int((deg + 22.5) / 45) % 8]

        condition_main = raw.get("weather", [{}])[0].get("main", "clear").lower()
        condition_map = {
            "clear": "clear",
            "clouds": "cloudy",
            "rain": "rain",
            "drizzle": "rain",
            "thunderstorm": "storm",
            "snow": "snow",
            "mist": "fog",
            "fog": "fog",
            "haze": "fog",
        }

        return {
            "condition": condition_map.get(condition_main, "clear"),
            "temperature": round(raw.get("main", {}).get("temp", 72)),
            "wind_speed": round(raw.get("wind", {}).get("speed", 0)),
            "wind_direction": wind_dir,
            "humidity": raw.get("main", {}).get("humidity", 45),
            "visibility": round(raw.get("visibility", 16093) / 1609.3, 1),
            "source": "live",
        }
    except Exception:
        return None


@router.get("/weather")
def command_deck_weather(
    lat: Optional[float] = Query(None, description="User latitude from browser geolocation"),
    lon: Optional[float] = Query(None, description="User longitude from browser geolocation"),
):
    """
    Return weather data for the Command Deck.

    - If lat/lon provided AND WEATHER_API_KEY is set: fetch real weather for those coordinates.
    - If lat/lon provided but no WEATHER_API_KEY: return mock data with source "mock".
    - If no lat/lon provided: return mock data as before.
    """
    if lat is not None and lon is not None:
        live = _fetch_live_weather(lat, lon)
        if live:
            return JSONResponse(content=live)
    return JSONResponse(content=dict(MOCK_WEATHER))

# ---------------------------------------------------------------------------
# Intake Engine — injected into status response via monkey-patch override
# We add a new endpoint that merges intake state into the status payload.
# ---------------------------------------------------------------------------

@router.get("/status/intake")
def command_deck_status_with_intake():
    """Extended status including Intake Engine telemetry."""
    data = dict(MOCK_STATUS)
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        from routes.intake_engine import load_latest_intake, count_submissions, load_recent_intakes
        latest = load_latest_intake()
        total = count_submissions()
        ie: dict = {
            "status":            "active" if latest else "idle",
            "total_submissions": total,
            "latest_id":         latest.get("intake_id") if latest else None,
            "latest_score":      latest.get("intake_score") if latest else None,
            "latest_missing":    latest.get("missing_fields", []) if latest else [],
            "latest_type":       latest.get("intake_type") if latest else None,
            "latest_status":     latest.get("status") if latest else None,
        }
        if latest and latest.get("intake_type") == "partner" and latest.get("operator_rail"):
            rail = latest["operator_rail"]
            ie["operator_rail"] = {
                "readiness_score":     rail.get("readiness_score"),
                "compliance_complete": rail.get("compliance_complete"),
                "entity_type_label":   rail.get("entity_type_label"),
                "operator_type_label": rail.get("operator_type_label"),
                "service_area":        rail.get("service_area"),
                "missing_compliance":  rail.get("missing_compliance", []),
            }
        if latest and latest.get("intake_type") in ("labor", "production") and latest.get("labor_rail"):
            lrail = latest["labor_rail"]
            ie["labor_rail"] = {
                "readiness_score":    lrail.get("readiness_score"),
                "crew_ready":         lrail.get("crew_ready"),
                "role_type_label":    lrail.get("role_type_label"),
                "availability_label": lrail.get("availability_label"),
                "labor_location":     lrail.get("labor_location"),
                "missing_readiness":  lrail.get("missing_readiness", []),
            }
        if latest and latest.get("intake_type") == "legal" and latest.get("legal_rail"):
            lr = latest["legal_rail"]
            ie["legal_rail"] = {
                "standing":               lr.get("standing"),
                "standing_label":         lr.get("standing_label"),
                "injury_met":             lr.get("injury_met"),
                "causation_met":          lr.get("causation_met"),
                "redressability_met":     lr.get("redressability_met"),
                "concrete_harms":         lr.get("concrete_harms", []),
                "capacity_label":         lr.get("capacity_label"),
                "immunity_risk":          lr.get("immunity_risk"),
                "recommended_defendants": lr.get("recommended_defendants", []),
                "target_name":            lr.get("target_name"),
                "target_type":            lr.get("target_type"),
            }
            sl = lr.get("standing_label", "")
            data["standing"] = _STANDING_SCORES.get(sl, data["standing"])
            ir = (lr.get("immunity_risk") or "").upper()
            if ir.startswith("LOW"):
                data["capacity"] = 88
            elif ir.startswith("MODERATE"):
                data["capacity"] = 62
            elif ir.startswith("HIGH"):
                data["capacity"] = 30
        data["intake_engine"] = ie

        recent_raw = load_recent_intakes(limit=10)
        recent = []
        for r in recent_raw:
            rail_type = "none"
            readiness = None
            if r.get("intake_type") == "partner" and r.get("operator_rail"):
                rail_type = "operator"
                readiness = r["operator_rail"].get("readiness_score")
            elif r.get("intake_type") in ("labor", "production") and r.get("labor_rail"):
                rail_type = "labor"
                readiness = r["labor_rail"].get("readiness_score")
            elif r.get("intake_type") == "legal" and r.get("legal_rail"):
                rail_type = "legal"
                lr_r = r["legal_rail"]
                standing = lr_r.get("standing")
                readiness = 92 if standing is True else (22 if standing is False else None)
            subj = (r.get("subject") or "")
            recent.append({
                "intake_id":   r.get("intake_id"),
                "intake_type": r.get("intake_type"),
                "subject":     subj[:60] + ("…" if len(subj) > 60 else ""),
                "status":      r.get("status"),
                "created_at":  r.get("created_at"),
                "rail_type":   rail_type,
                "readiness":   readiness,
            })
        data["recent_intakes"] = recent
    except Exception as exc:
        data["intake_engine"] = {"status": "error", "error": str(exc)}
        data["recent_intakes"] = []

    return JSONResponse(content=data)

