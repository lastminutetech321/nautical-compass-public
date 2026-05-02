# Legal Source Registry

Tracks sources that have been indexed in `law_library/` or are planned for addition.

## Format

Each source entry uses:
- **id**: `{category}/{slug}` — matches the filesystem path `law_library/{category}/{slug}.md`
- **status**: `indexed` | `planned` | `pending-pdf`
- **used by**: which services or analysis flows reference this source

---

## Case Law (`law_library/cases/`)

| Slug | Title | Citation | Status | Used By |
|------|-------|----------|--------|---------|
| `lujan-v-defenders` | Lujan v. Defenders of Wildlife | 504 U.S. 555 (1992) | planned | standing_analysis_service |
| `spokeo-v-robins` | Spokeo, Inc. v. Robins | 578 U.S. 330 (2016) | planned | standing_analysis_service |
| `monell-v-nyc` | Monell v. Department of Social Services | 436 U.S. 658 (1978) | planned | rights_analysis_service |
| `ex-parte-young` | Ex parte Young | 209 U.S. 123 (1908) | planned | rights_analysis_service |
| `transunion-v-ramirez` | TransUnion LLC v. Ramirez | 594 U.S. 413 (2021) | planned | standing_analysis_service |

---

## Statutes (`law_library/statutes/`)

| Slug | Title | Citation | Status | Used By |
|------|-------|----------|--------|---------|
| `fcra` | Fair Credit Reporting Act | 15 U.S.C. § 1681 | planned | regulatory_routes_service |
| `fdcpa` | Fair Debt Collection Practices Act | 15 U.S.C. § 1692 | planned | regulatory_routes_service |
| `efta` | Electronic Fund Transfer Act | 15 U.S.C. § 1693 | planned | regulatory_routes_service |
| `tila` | Truth in Lending Act | 15 U.S.C. § 1601 | planned | regulatory_routes_service |
| `1983-civil-rights` | Civil Rights Act § 1983 | 42 U.S.C. § 1983 | planned | rights_analysis_service |

---

## Regulations (`law_library/regulations/`)

| Slug | Title | Citation | Status | Used By |
|------|-------|----------|--------|---------|
| `reg-e` | Regulation E (EFTA implementing) | 12 C.F.R. Part 1005 | planned | regulatory_routes_service |
| `reg-z` | Regulation Z (TILA implementing) | 12 C.F.R. Part 1026 | planned | regulatory_routes_service |
| `reg-f` | Regulation F (FDCPA implementing) | 12 C.F.R. Part 1006 | planned | regulatory_routes_service |

---

## Legal Forms (`law_library/forms/`)

| Slug | Title | Status | Used By |
|------|-------|--------|---------|
| `complaint-template` | Federal Civil Rights Complaint | planned | legal_results_service |
| `pro-se-affidavit` | Pro Se Affidavit of Facts | planned | legal_results_service |
| `motion-to-proceed-ifp` | Motion to Proceed In Forma Pauperis | planned | legal_results_service |

---

## How to Add a Source

1. Create the file at `law_library/{category}/{slug}.md` with YAML frontmatter:

```yaml
---
title: Case Name v. Defendant
citation: 504 U.S. 555 (1992)
tags: [standing, injury-in-fact]
jurisdiction: federal
year: 1992
---

## Summary

...source text...
```

2. Update status in this registry from `planned` → `indexed`.
3. The service (`services/law_library_service.py`) picks it up automatically at next request.

For PDFs: drop the file in the folder — no frontmatter needed. Update status to `pending-pdf` (content not extracted).
