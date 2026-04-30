# Nautical Compass Build Manifest

## Current Platform Modules
- Base Application Core (`main.py`)
- Command Deck V2 Dashboard (`command_deck_route.py`, `command_deck.html`, `command_deck.js`, `command_deck_audio.js`, `command_deck.css`)
- Validation Framework (`boot_test.py`, `integration_test.py`)

## Active Routes
- `/`: Home index page with main navigation
- `/status`: JSON endpoint returning basic system status and version
- `/compass`: Static compass reading template
- `/command-deck`: Enhanced Command Deck V2 dashboard with real-time UI, dynamic weather, and multi-axis vessel motion

## Static/Template Files
- `templates/index.html`: Base home template
- `templates/compass.html`: Base compass template
- `templates/command_deck.html`: Command Deck V2 template with new navigation bar
- `static/command_deck.css`: Command Deck styling (includes new `.deck-nav` component)
- `static/command_deck.js`: Command Deck UI logic (includes `updateNavIndicators()`)
- `static/command_deck_audio.js`: Command Deck audio engine

## Dependency List
- `Flask>=2.3.0` (Installed version: `3.1.3`)
- Standard Python 3.11 libraries (threading, urllib, time)

## Known Issues
- Command Deck data is currently mocked/randomized via `setInterval`.
- Git remote `origin` is not configured, preventing `git push`.
- Port 5000/5001 binding conflicts occasionally require manual `fuser -k` or `lsof` cleanup during rapid restart cycles.

## Next Build Queue
- Cycle 2: Implement real-time data API integration to replace mocked data
- Cycle 3: Enhance audio capabilities with external `.mp3` loading
