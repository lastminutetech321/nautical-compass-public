# Nautical Compass — World Data Sources

## Purpose
Defines the external data sources that power intelligence, scoring, routing, forecasting, and market awareness across Nautical Compass.

NC should rely on primary and official sources wherever possible, then normalize external data into internal scoring and operating logic.

---

## Core Categories

### 1. Labor and Workforce Data
Used for:
- income benchmarking
- role demand tracking
- labor market positioning
- regional work trends

Priority sources:
- U.S. Bureau of Labor Statistics (BLS)
- U.S. Census workforce datasets
- state labor departments
- internal platform activity data
- trusted industry datasets

---

### 2. Business and Entity Data
Used for:
- business verification
- registry lookups
- entity intelligence
- structural review

Priority sources:
- state business registries
- IRS business guidance
- OpenCorporates
- secretary of state databases

---

### 3. Financial and Economic Data
Used for:
- pricing intelligence
- macro risk awareness
- growth signals
- revenue context

Priority sources:
- Federal Reserve Economic Data (FRED)
- World Bank
- IMF datasets
- U.S. BEA
- U.S. Census business data

---

### 4. Legal and Regulatory Data
Used for:
- complaint routing
- legal intake support
- rights and compliance analysis
- regulator targeting

Priority sources:
- federal statutes
- state statutes
- agency enforcement pages
- court record systems where accessible
- official regulatory guidance

---

### 5. Weather and Environmental Data
Used for:
- Helm display
- route risk
- operational warnings
- marine expansion later

Priority sources:
- Apple Weather / WeatherKit
- The Weather Company / IBM APIs
- NOAA data for marine and weather expansion

---

### 6. Geolocation and Mapping Data
Used for:
- dispatch logic
- service area mapping
- route intelligence
- future vessel positioning

Priority sources:
- Mapbox
- Google Maps Platform
- OpenStreetMap

---

### 7. Public Opportunity and Program Data
Used for:
- grants
- procurement
- market expansion
- public-sector targeting

Priority sources:
- Grants.gov
- SAM.gov
- state procurement portals
- local government contracting portals

---

## Source Priority Rules

1. Prefer official and primary-source data
2. Avoid scraping consumer-facing apps and websites when APIs or official datasets exist
3. Use API-first integrations where possible
4. Normalize outside data into NC’s own scoring and routing system
5. Keep all sources modular and swappable
6. Track source trust level before using it for system recommendations

---

## Trust Tiers

### Tier 1 — Official / Primary
Examples:
- government sites
- regulator datasets
- official APIs
- court and statute sources

### Tier 2 — Institutional / Enterprise
Examples:
- IBM weather products
- OpenCorporates
- major economic databases

### Tier 3 — Supplemental / Contextual
Examples:
- industry reports
- partner data feeds
- internal aggregation layers

Tier 3 sources should not be used as the sole basis for critical routing decisions.

---

## Future Expansion Targets

- NOAA marine and coastal systems
- AIS vessel data
- insurance risk data
- industry payroll benchmarking
- international market datasets
- logistics and route intelligence feeds

---

## Core Principle

External data does not replace Nautical Compass logic.

External data strengthens Nautical Compass intelligence.

NC should remain the decision layer, not just a mirror of outside datasets.
