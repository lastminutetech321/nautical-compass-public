"""
Law Library Service

Scans law_library/ at request time and returns available sources.
Graceful fallback: if the folder is empty, missing, or a file is
unreadable, returns empty lists — never raises to callers.

Supports:
  .md / .txt — parsed for YAML frontmatter + body
  .pdf        — indexed by filename only (no content extraction)

Frontmatter is optional. Files without it are still listed.
"""
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LIBRARY_ROOT = Path("law_library")

CATEGORIES = {
    "cases":       "Case Law",
    "statutes":    "Statutes",
    "regulations": "Regulations",
    "forms":       "Legal Forms",
    "uploads":     "Uploaded Documents",
}


# ── frontmatter parser ───────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (metadata_dict, body_text). Works with or without frontmatter."""
    if not text.startswith("---"):
        return {}, text.strip()
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text.strip()
    fm_block = text[3:end].strip()
    body = text[end + 4:].strip()
    meta: dict = {}
    for line in fm_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [t.strip().strip("\"'") for t in v[1:-1].split(",") if t.strip()]
            meta[k] = v
    return meta, body


# ── single file scanner ──────────────────────────────────────────────────────

def _read_source(path: Path, category: str) -> Optional[Dict[str, Any]]:
    try:
        source_id = f"{category}/{path.stem}"
        if path.suffix.lower() == ".pdf":
            return {
                "id": source_id,
                "slug": path.stem,
                "filename": path.name,
                "category": category,
                "category_label": CATEGORIES.get(category, category),
                "title": path.stem.replace("-", " ").title(),
                "citation": "",
                "tags": [],
                "jurisdiction": "",
                "year": "",
                "content_type": "pdf",
                "body": "",
                "available": True,
            }

        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        return {
            "id": source_id,
            "slug": path.stem,
            "filename": path.name,
            "category": category,
            "category_label": CATEGORIES.get(category, category),
            "title": meta.get("title") or path.stem.replace("-", " ").title(),
            "citation": meta.get("citation", ""),
            "tags": meta.get("tags", []),
            "jurisdiction": meta.get("jurisdiction", ""),
            "year": meta.get("year", ""),
            "content_type": "text",
            "body": body,
            "available": True,
        }
    except Exception as exc:
        logger.warning("law_library: could not read %s: %s", path, exc)
        return None


# ── public API ───────────────────────────────────────────────────────────────

def list_sources(category: str | None = None) -> List[Dict[str, Any]]:
    """Return all available sources, optionally filtered by category."""
    results: List[Dict[str, Any]] = []
    if not _LIBRARY_ROOT.exists():
        return results

    cats = [category] if category else list(CATEGORIES.keys())
    for cat in cats:
        folder = _LIBRARY_ROOT / cat
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.name.startswith(".") or path.name == "README.md":
                continue
            if path.suffix.lower() not in {".md", ".txt", ".pdf"}:
                continue
            source = _read_source(path, cat)
            if source:
                results.append(source)
    return results


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    """Return a single source by id (e.g. 'cases/lujan-v-defenders')."""
    try:
        parts = source_id.split("/", 1)
        if len(parts) != 2:
            return None
        category, slug = parts
        folder = _LIBRARY_ROOT / category
        for ext in (".md", ".txt", ".pdf"):
            path = folder / f"{slug}{ext}"
            if path.exists():
                return _read_source(path, category)
    except Exception as exc:
        logger.warning("law_library: get_source %s failed: %s", source_id, exc)
    return None


def get_summary() -> Dict[str, Any]:
    """Return per-category counts and overall connected status."""
    counts: Dict[str, int] = {}
    for cat in CATEGORIES:
        folder = _LIBRARY_ROOT / cat
        if not folder.is_dir():
            counts[cat] = 0
            continue
        counts[cat] = sum(
            1 for p in folder.iterdir()
            if not p.name.startswith(".") and p.suffix.lower() in {".md", ".txt", ".pdf"}
        )
    total = sum(counts.values())
    return {
        "connected": _LIBRARY_ROOT.exists(),
        "total_sources": total,
        "counts": counts,
        "categories": CATEGORIES,
        "library_path": str(_LIBRARY_ROOT.resolve()),
    }


def search_sources(query: str) -> List[Dict[str, Any]]:
    """Simple case-insensitive text search across title, citation, tags, body."""
    q = query.lower().strip()
    if not q:
        return []
    results = []
    for source in list_sources():
        haystack = " ".join([
            source.get("title", ""),
            source.get("citation", ""),
            " ".join(source.get("tags", [])),
            source.get("body", "")[:2000],
        ]).lower()
        if q in haystack:
            results.append(source)
    return results
