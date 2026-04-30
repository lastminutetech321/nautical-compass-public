"""
Nautical Compass — Live Command Deck Route (FastAPI)
=====================================================
Provides the /command-deck route as a FastAPI APIRouter.

Usage in main.py:
    from command_deck_route import router as command_deck_router
    app.include_router(command_deck_router)
"""
import subprocess
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _get_build_hash() -> str:
    """Return the short git commit hash, or 'unknown' if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


@router.get("/command-deck", response_class=HTMLResponse)
def command_deck(request: Request):
    """
    Render the Live Command Deck dashboard.

    Placeholder weather data is provided here so the template always
    receives a valid context.  Replace with a real weather-API call
    (e.g. OpenWeatherMap, WeatherAPI) when ready.
    """
    weather_data = {
        "condition": "clear",       # clear | cloudy | rain | fog | storm | snow
        "temperature": 72,          # Fahrenheit
        "wind_speed": 12,           # mph
        "wind_direction": "NE",
        "humidity": 45,             # percent
        "visibility": 10            # miles
    }
    return templates.TemplateResponse(
        request,
        "command_deck.html",
        context={
            "weather": weather_data,
            "build_hash": _get_build_hash(),
            "build_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
    )
