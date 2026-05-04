"""
Company Directory Module
========================
Prefix: /company-directory

Routes:
  GET  /company-directory                     — public sanitized directory
  GET  /admin/company-import                  — import preview (admin)
  POST /admin/company-import/save             — save approved records (admin)
  GET  /admin/company-directory               — internal full directory (admin)

Storage:
  runtime/company_directory_raw.json   — output of parse_labor_companies.py
  runtime/company_directory.json       — imported/approved company records
"""

import json
import time
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.living_ledger import get_actor_id, log_page_view, write_event

router = APIRouter(tags=["company-directory"])
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Runtime paths
# ---------------------------------------------------------------------------
RUNTIME_DIR = Path("runtime")
RUNTIME_DIR.mkdir(exist_ok=True)

RAW_JSON = RUNTIME_DIR / "company_directory_raw.json"
DIRECTORY_JSON = RUNTIME_DIR / "company_directory.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


def _load_raw() -> list[dict]:
    if not RAW_JSON.exists():
        return []
    with open(RAW_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_directory() -> list[dict]:
    if not DIRECTORY_JSON.exists():
        return []
    with open(DIRECTORY_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_directory(entries: list[dict]) -> None:
    with open(DIRECTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def _apply_filters(entries: list[dict], city: str, status: str) -> list[dict]:
    if city:
        entries = [e for e in entries if e.get("city", "").lower() == city.lower()]
    if status:
        entries = [e for e in entries if e.get("status", "").lower() == status.lower()]
    return entries


def _get_filter_options(entries: list[dict]) -> tuple[list[str], list[str]]:
    cities = sorted({e.get("city", "") for e in entries if e.get("city")})
    statuses = sorted({e.get("status", "") for e in entries if e.get("status")})
    return cities, statuses


def _group_by_city(entries: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for e in entries:
        key = e.get("city") or "Unknown"
        grouped.setdefault(key, []).append(e)
    return dict(sorted(grouped.items()))


# ---------------------------------------------------------------------------
# Admin: Import preview
# ---------------------------------------------------------------------------

@router.get("/admin/company-import")
def admin_company_import(request: Request):
    log_page_view(request, rail="company_directory",
                  event_type="company_import_preview_opened",
                  title="Company import preview opened",
                  next_action="company_records_saved")
    raw = _load_raw()
    has_raw = bool(raw)
    # Attach a stable index so the template can use it as record ID
    for i, entry in enumerate(raw):
        entry["_idx"] = i
    return templates.TemplateResponse(
        request,
        "company_directory_import.html",
        context=_ctx(request, {
            "entries": raw,
            "has_raw": has_raw,
            "total": len(raw),
        }),
    )


# ---------------------------------------------------------------------------
# Admin: Save approved records
# ---------------------------------------------------------------------------

@router.post("/admin/company-import/save")
async def admin_company_import_save(
    request: Request,
    approved_ids: List[str] = Form(default=[]),
):
    raw = _load_raw()
    existing = _load_directory()

    # Build dedup key set from existing directory
    existing_keys = {
        (e.get("company_name", "").lower(), e.get("city", "").lower())
        for e in existing
    }

    # Parse approved_ids as integers (they are raw list indices)
    approved_set = set()
    for id_str in approved_ids:
        try:
            approved_set.add(int(id_str))
        except (ValueError, TypeError):
            pass

    imported_at = int(time.time())
    new_entries = []
    for i, entry in enumerate(raw):
        if i not in approved_set:
            continue
        dedup_key = (
            entry.get("company_name", "").lower(),
            entry.get("city", "").lower(),
        )
        if dedup_key in existing_keys:
            continue  # skip duplicate
        record = dict(entry)
        record["company_id"] = "cmp_" + uuid4().hex[:10]
        record["imported_at"] = imported_at
        new_entries.append(record)
        existing_keys.add(dedup_key)

    all_entries = existing + new_entries
    _save_directory(all_entries)

    write_event(
        rail="company_directory",
        event_type="company_records_saved",
        title=f"Company records saved — {len(new_entries)} imported",
        route="/admin/company-import/save",
        actor_id=get_actor_id(request),
        actor_type="admin",
        status="saved",
        next_action="admin_company_directory_review",
        payload={"imported_count": len(new_entries), "total_after": len(all_entries)},
    )

    return RedirectResponse(url="/admin/company-directory", status_code=303)


# ---------------------------------------------------------------------------
# Admin: Internal directory
# ---------------------------------------------------------------------------

@router.get("/admin/company-directory")
def admin_company_directory(
    request: Request,
    city: str = Query(default=""),
    status: str = Query(default=""),
):
    entries = _load_directory()
    cities, statuses = _get_filter_options(entries)
    filtered = _apply_filters(entries, city, status)
    grouped = _group_by_city(filtered)
    return templates.TemplateResponse(
        request,
        "company_directory_internal.html",
        context=_ctx(request, {
            "grouped": grouped,
            "total": len(filtered),
            "all_total": len(entries),
            "cities": cities,
            "statuses": statuses,
            "filter_city": city,
            "filter_status": status,
        }),
    )


# ---------------------------------------------------------------------------
# Public: Sanitized directory
# ---------------------------------------------------------------------------

@router.get("/company-directory")
def public_company_directory(
    request: Request,
    city: str = Query(default=""),
    status: str = Query(default=""),
):
    log_page_view(request, rail="company_directory",
                  event_type="company_directory_public_viewed",
                  title="Public company directory viewed",
                  next_action="company_profile_claim",
                  extra={"city_filter": city, "status_filter": status} if (city or status) else {})
    all_entries = _load_directory()

    # Remove do_not_contact entries entirely
    visible = [e for e in all_entries if not e.get("do_not_contact", False)]

    cities, statuses = _get_filter_options(visible)
    filtered = _apply_filters(visible, city, status)

    # Strip internal-only fields before passing to template
    INTERNAL_FIELDS = {
        "do_not_contact", "do_not_use", "internal_notes",
        "phone", "email", "load_in_min", "load_out_min",
        "source_file", "parsed_at", "imported_at",
    }
    public_entries = []
    for e in filtered:
        pub = {k: v for k, v in e.items() if k not in INTERNAL_FIELDS}
        public_entries.append(pub)

    grouped = _group_by_city(public_entries)
    return templates.TemplateResponse(
        request,
        "company_directory_public.html",
        context=_ctx(request, {
            "grouped": grouped,
            "total": len(public_entries),
            "cities": cities,
            "statuses": statuses,
            "filter_city": city,
            "filter_status": status,
        }),
    )
