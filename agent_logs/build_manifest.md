# Nautical Compass Build Manifest

## Current Platform Modules
- Base Application Core (`main.py`) — FastAPI, Jinja2Templates, StaticFiles
- Command Deck V2 Dashboard (`command_deck_route.py`, `command_deck.html`, `command_deck.js`, `command_deck_audio.js`, `command_deck.css`)
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
| `/health` | GET | App health check with module status |
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
| `/command-deck` | GET | **Command Deck V2 dashboard** (new) |

## Static/Template Files
- `templates/command_deck.html` — Command Deck V2 template with navigation bar
- `static/command_deck.css` — Command Deck styling (includes `.deck-nav` component)
- `static/command_deck.js` — Command Deck UI logic with `updateNavIndicators()`
- `static/command_deck_audio.js` — Command Deck ambient audio engine

## Dependency List
- `fastapi` (0.136.0)
- `starlette` (1.0.0)
- `uvicorn`
- `jinja2`
- `python-multipart`
- Standard Python 3.11 libraries

## Known Issues
- `/status` and `/compass` return 404 — these routes do not exist in the remote app (they were part of the original local Flask scaffold and were not ported over).
- Command Deck data is currently mocked/randomized via `setInterval` in `command_deck.js`. Real-time API integration is planned for Cycle 2.
- `main.py` contains two duplicate `@app.get("/system-status")` definitions (pre-existing issue in remote code; the second one shadows the first).
- `from routes.core_routes import core_routes` is imported twice in `main.py` (pre-existing duplicate import).

## Next Build Queue
- **Cycle 2:** Real-time data API integration on branch `cycle-2-command-deck-data` — replace mocked weather/system data with live API calls
- **Cycle 3:** Audio enhancement — external `.mp3` file loading for ambient audio engine
- **Cycle 4:** Deduplicate `main.py` (remove duplicate `/system-status` route and duplicate import)
