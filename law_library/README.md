# Law Library — Nautical Compass

Drop legal source files here. The law library service scans this folder at
request time and surfaces available sources in the UI.

## Folder structure

```
law_library/
  cases/         ← Case law: markdown or plain text. Filename = case slug.
  statutes/      ← Statutory text: FCRA, FDCPA, §1983, EFTA, TILA, etc.
  regulations/   ← CFR excerpts and agency rules.
  forms/         ← Legal form templates: complaint, affidavit, motion, notice.
  uploads/       ← User-uploaded PDFs and documents (written by the app).
```

## File naming

- Use lowercase slugs with hyphens: `lujan-v-defenders-of-wildlife.md`
- Add a YAML frontmatter block at the top of each `.md` file for metadata:

```yaml
---
title: Lujan v. Defenders of Wildlife
citation: 504 U.S. 555 (1992)
category: cases
tags: [standing, injury-in-fact, causation, redressability]
jurisdiction: federal
year: 1992
---
```

- PDFs are indexed by filename only (no frontmatter parsing).

## How it's used

`services/law_library_service.py` scans this folder at request time.
If the folder is empty or a category has no files, pages display
"Source library not connected yet" without crashing.

The registry at `docs/legal_source_registry.md` documents known sources
that have been indexed or are planned for addition.
