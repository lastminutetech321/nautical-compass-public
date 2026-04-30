# Nautical Compass Build Manifest

## Current Platform Modules
- Base Application Core (`main.py`) — FastAPI, Jinja2Templates, StaticFiles
- Command Deck V2 Dashboard (`command_deck_route.py`, `command_deck.html`, `command_deck.js`, `command_deck_audio.js`, `command_deck.css`)
- Command Deck Data API (`command_deck_api.py`) — real-time status and weather endpoints with mock fallback, accepts user lat/lon for location-based weather
- Financial Engine (`routes/financial_engine_test.py`, `routes/financial_engine_panel.py`, `routes/financial_engine_actions.py`)
- Core Routes (`routes/core_routes.py`)
- Labor Signal Module (`labor_signal/` — conditionally loaded via feature flag)
- Ledger System (`modules/ledger/`)
- Services Catalog (`services_catalog/catalog.py` — conditionally loaded)
- Agent Audit Logs (`agent_logs/build_audit.md`, `agent_logs/build_manifest.md`)

## Active Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Home index page |
| `/health` | GET | App health check with commit hash, build time, starlette compat, module status |
| `/hall` | GET | Hall page |
| `/lead` | GET | Lead capture page |
| `/lead/thanks` | GET | Lead thank-you page |
| `/sponsor` | GET | Sponsor page |
| `/checkout` | GET | Checkout landing |
| `/checkout/{plan_key}` | GET | Plan-specific checkout |
| `/partner` | GET | Partner intake |
| `/intake/production` | GET | Production intake form |
| `/labor/employer-request/start` | GET | Employer request start |
| `/labor/employer-view` | GET | Employer view dashboard |
| `/labor/match-review` | GET | Match review panel |
| `/labor/dashboard` | GET | Labor dashboard |
| `/labor/profile/summary` | GET | Labor profile summary |
| `/labor/profile/edit` | GET | Labor profile editor |
| `/labor/profile/start` | GET | Labor profile start |
| `/intake/labor` | GET | Labor intake form |
| `/modules/case-dock` | GET | Case Dock module |
| `/modules/case-update` | GET | Case update module |
| `/modules/signal-dock` | GET | Signal Dock module |
| `/modules/equity-engine` | GET | Equity Engine module |
| `/admin/ledger-preview` | GET | Admin ledger preview |
| `/modules/labor-signal` | GET | Labor Signal module |
| `/modules/navigator-ai` | GET | Navigator AI module |
| `/modules/draft-packet` | GET | Draft Packet module |
| `/system-status` | GET | System status JSON |
| `/legalese` | GET/POST | Legalese practice room |
| `/services` | GET | Services catalog |
| `/services/{service_slug}` | GET | Service detail page |
| `/command-deck` | GET | Command Deck V2 dashboard |
| `/api/command-deck/status` | GET | **Command Deck system state JSON** (Cycle 2) |
| `/api/command-deck/weather` | GET | **Command Deck weather data JSON** (Cycle 2) |

## Static/Template Files
- `templates/command_deck.html` — Command Deck V2 template with navigation bar and data source badge
- `static/command_deck.css` — Command Deck styling (includes `.deck-nav`, `.data-source-badge`, gauge visibility, tooltip styles, vessel motion keyframes, gauge readability enhancements)
- `static/command_deck.js` — Command Deck UI logic with API fetch polling (30s interval), browser geolocation, graceful fallback, interactive tooltips, tap support, value update animations, weather-driven vessel motion
- `static/command_deck_audio.js` — Command Deck ambient audio engine

## Dependency List
- `fastapi` (0.136.0)
- `starlette` (1.0.0)
- `uvicorn`
- `jinja2`
- `python-multipart`
- Standard Python 3.11 libraries (`urllib.request`, `json`, `os`, `time`, `datetime`)

## Known Issues
- `/status` and `/compass` return 404 — these routes do not exist in the remote app (they were part of the original local Flask scaffold and were not ported over).
- `main.py` contains two duplicate `@app.get("/system-status")` definitions (pre-existing issue in remote code; the second one shadows the first).
- `from routes.core_routes import core_routes` is imported twice in `main.py` (pre-existing duplicate import).
- Command Deck status data is currently static mock values; integration with the helm_state_adapter for live metrics is a future enhancement.

## Next Build Queue
- **Cycle 4 (COMPLETE — merged to main `765aa3a`):** Gauge readability, interactive tooltips, tap support, value update animations
- **Cycle 5 (COMPLETE — merged to main `b3a7624`):** Real vessel motion, gauge readability, deployment safeguards
- **Cycle 6 (COMPLETE — branch: `cycle-6-water-lighthouse-motion`):** Water motion, lighthouse parallax, motion sync, gauge readability final
- **Cycle 7:** Connect `/api/command-deck/status` to live `helm_state_adapter` metrics
- **Cycle 8:** Advanced weather visualization and ambient sound enhancements
