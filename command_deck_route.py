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
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.access_control import get_operator_role, get_operator_perms, ROLE_PERMISSIONS

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
    role = get_operator_role(request)
    if "view_command_deck" not in ROLE_PERMISSIONS.get(role, set()):
        return RedirectResponse("/operator/login?next=/command-deck", status_code=302)

    weather_data = {
        "condition": "clear",
        "temperature": 72,
        "wind_speed": 12,
        "wind_direction": "NE",
        "humidity": 45,
        "visibility": 10,
    }
    return templates.TemplateResponse(
        request,
        "command_deck.html",
        context={
            "weather": weather_data,
            "build_hash": _get_build_hash(),
            "build_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "operator_role": role,
            "operator_perms": get_operator_perms(request),
        },
    )
