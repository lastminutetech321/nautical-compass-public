import time
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.law_library_service import (
    list_sources,
    get_source,
    get_summary,
    search_sources,
    CATEGORIES,
)

templates = Jinja2Templates(directory="templates")
law_library_router = APIRouter()

_UPLOAD_DIR = Path("law_library/uploads")


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


# ── UI routes ────────────────────────────────────────────────────────────────

@law_library_router.get("/law-library", response_class=HTMLResponse)
def law_library_hub(request: Request):
    summary = get_summary()
    sources = list_sources() if summary["connected"] else []
    return templates.TemplateResponse(
        request,
        "law_library.html",
        context=_ctx(request, {
            "summary": summary,
            "sources": sources,
            "categories": CATEGORIES,
        }),
    )


@law_library_router.get("/law-library/upload", response_class=HTMLResponse)
def law_library_upload_form(request: Request):
    return templates.TemplateResponse(
        request,
        "law_library_upload.html",
        context=_ctx(request, {"categories": CATEGORIES}),
    )


@law_library_router.get("/law-library/{category}", response_class=HTMLResponse)
def law_library_category(request: Request, category: str):
    if category not in CATEGORIES:
        return RedirectResponse("/law-library", status_code=302)
    sources = list_sources(category=category)
    return templates.TemplateResponse(
        request,
        "law_library.html",
        context=_ctx(request, {
            "summary": get_summary(),
            "sources": sources,
            "categories": CATEGORIES,
            "active_category": category,
            "category_label": CATEGORIES[category],
        }),
    )


@law_library_router.get("/law-library/source/{category}/{slug}", response_class=HTMLResponse)
def law_library_source(request: Request, category: str, slug: str):
    source = get_source(f"{category}/{slug}")
    if not source:
        return RedirectResponse("/law-library", status_code=302)
    return templates.TemplateResponse(
        request,
        "law_library_source.html",
        context=_ctx(request, {"source": source, "categories": CATEGORIES}),
    )


@law_library_router.post("/law-library/upload", response_class=HTMLResponse)
async def law_library_upload_post(
    request: Request,
    category: str = Form("uploads"),
    file: UploadFile = File(...),
):
    errors = []
    filename = (file.filename or "").strip()
    if not filename:
        errors.append("No file selected.")
    elif not any(filename.lower().endswith(ext) for ext in (".md", ".txt", ".pdf")):
        errors.append("Only .md, .txt, and .pdf files are accepted.")

    if not errors:
        dest_dir = Path("law_library") / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        content = await file.read()
        dest.write_bytes(content)
        return RedirectResponse(f"/law-library/{category}", status_code=302)

    return templates.TemplateResponse(
        request,
        "law_library_upload.html",
        context=_ctx(request, {"categories": CATEGORIES, "errors": errors}),
    )


# ── API routes ────────────────────────────────────────────────────────────────

@law_library_router.get("/api/law-library/summary")
def api_summary():
    return JSONResponse(get_summary())


@law_library_router.get("/api/law-library/sources")
def api_sources(category: str = None):
    return JSONResponse({"ok": True, "sources": list_sources(category=category)})


@law_library_router.get("/api/law-library/source/{category}/{slug}")
def api_source(category: str, slug: str):
    source = get_source(f"{category}/{slug}")
    if not source:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return JSONResponse({"ok": True, "source": source})


@law_library_router.get("/api/law-library/search")
def api_search(q: str = ""):
    results = search_sources(q)
    return JSONResponse({"ok": True, "query": q, "results": results, "count": len(results)})
