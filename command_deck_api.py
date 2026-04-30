"""
Nautical Compass — Command Deck Data API (FastAPI)
====================================================
Provides JSON endpoints for the Command Deck frontend:
  - /api/command-deck/status  — system state metrics
  - /api/command-deck/weather — weather conditions (mock or live)

Usage in main.py:
    from command_deck_api import router as command_deck_api_router
    app.include_router(command_deck_api_router)

Environment Variables:
    WEATHER_API_KEY  — If set, attempts to fetch live weather from OpenWeatherMap.
                       Falls back to mock data on failure or if unset.
    WEATHER_LAT     — Latitude for weather lookup (default: 25.7617, Miami)
    WEATHER_LON     — Longitude for weather lookup (default: -80.1918, Miami)
"""

import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter
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


def _fetch_live_weather() -> dict | None:
    """
    Attempt to fetch live weather from OpenWeatherMap.
    Returns a normalized dict on success, or None on failure.
    """
    api_key = os.getenv("WEATHER_API_KEY", "").strip()
    if not api_key:
        return None

    lat = os.getenv("WEATHER_LAT", "25.7617")
    lon = os.getenv("WEATHER_LON", "-80.1918")
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
def command_deck_weather():
    """Return weather data for the Command Deck. Live if API key is set, mock otherwise."""
    live = _fetch_live_weather()
    if live:
        return JSONResponse(content=live)
    return JSONResponse(content=dict(MOCK_WEATHER))
