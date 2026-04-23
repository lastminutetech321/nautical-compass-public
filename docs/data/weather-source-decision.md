# Nautical Compass — Weather Source Decision

## Purpose
Defines how Nautical Compass should source weather data for Helm, alerts, route awareness, and future marine operations.

---

## Option 1 — Apple Weather / WeatherKit

### Strengths
- clean modern API
- good fit for app-level experiences
- current, hourly, and daily forecast support
- alert support
- strong Apple ecosystem alignment
- good choice for user-facing weather display

### Limits
- requires Apple developer setup
- attribution rules apply
- less enterprise-focused than larger environmental data platforms

### Best use inside NC
- primary weather source for app experience
- Helm conditions
- simple alerts
- polished user-facing forecast display

---

## Option 2 — The Weather Company / IBM APIs

### Strengths
- enterprise-grade weather data
- broader environmental intelligence
- radar, satellite, alerts, and historical data options
- stronger long-term fit for advanced operational forecasting

### Limits
- more complex integration
- may involve higher licensing cost
- heavier than needed for basic forecast display

### Best use inside NC
- secondary or advanced weather intelligence layer
- future operational expansion
- richer risk modeling
- advanced enterprise and marine data workflows

---

## Option 3 — NOAA and Marine Expansion

### Strengths
- official U.S. weather and marine source
- marine warnings and forecast support
- useful for future vessel routing and coastal intelligence
- strong fit for actual marine operations

### Limits
- less polished for consumer-style UI
- may require more integration work
- should complement, not necessarily replace, app-facing forecast services

### Best use inside NC
- marine expansion
- tide, wind, and coastal condition logic
- vessel safety and navigation layers later

---

## Prohibited Approach

Do not:
- scrape the Weather Channel website
- scrape Apple Weather app screens
- rely on copied consumer UI outputs
- use unofficial extraction methods for production weather data

Use supported APIs and licensed sources only.

---

## Recommended NC Architecture

### Primary source
Apple Weather / WeatherKit

### Secondary source
The Weather Company / IBM APIs

### Marine expansion source
NOAA and marine-specific official datasets

---

## Data Use Inside NC

Weather data should feed:

- Helm display
- Alert Ring
- Risk Index
- Direction indicators
- future route and marine overlays

---

## Decision Rule

Use Apple Weather when the goal is:
- clean app presentation
- current and forecast conditions
- user-facing experience

Use IBM / The Weather Company when the goal is:
- enterprise weather intelligence
- deeper environmental data
- richer alerting and historical context

Use NOAA when the goal is:
- official marine or coastal operating intelligence
- future vessel support
- wind, tide, and marine hazard integration

---

## Final Recommendation

For Nautical Compass now:
- use Apple Weather / WeatherKit as the primary weather layer

For Nautical Compass later:
- add IBM / Weather Company if deeper operational weather intelligence is needed
- add NOAA for marine and vessel expansion

This keeps the system clean now and expandable later.
