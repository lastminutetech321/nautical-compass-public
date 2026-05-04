import os
import time

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from uuid import uuid4
from services.living_ledger import log_page_view, write_event, get_actor_id
from services.labor_matching import (
    get_match_pool,
    get_worker_readiness_breakdown,
    get_dispatch_companies,
)

templates = Jinja2Templates(directory="templates")
labor_rail_router = APIRouter()


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


@labor_rail_router.get("/labor-rail")
def labor_rail(request: Request):
    log_page_view(request, rail="labor", event_type="labor_rail_page_viewed",
                  title="Labor Rail page viewed",
                  next_action="labor_rail_access_viewed",
                  residual_trigger="no_job_activity_after_signup")
    return templates.TemplateResponse(request, "labor_rail.html", context=_ctx(request))


@labor_rail_router.get("/labor/matches", response_class=None)
def labor_matches(
    request: Request,
    role: str = Query(""),
    market: str = Query(""),
):
    pool = get_match_pool(role_filter=role, market_filter=market)
    return templates.TemplateResponse(
        request,
        "labor_matches.html",
        context=_ctx(request, {
            "pool":          pool,
            "total":         len(pool),
            "role_filter":   role,
            "market_filter": market,
        }),
    )


@labor_rail_router.post("/labor/matches/request", response_class=HTMLResponse)
async def labor_matches_request(
    request: Request,
    roles_needed: str = Form(""),
    event_date: str   = Form(""),
    shift_window: str = Form(""),
    location: str     = Form(""),
    notes: str        = Form(""),
):
    request_id = f"req_{uuid4().hex}"

    write_event(
        rail="labor",
        event_type="dispatch_review_requested",
        title="Dispatch review requested",
        route="/labor/matches/request",
        status="submitted",
        actor_id=get_actor_id(request),
        actor_type="employer",
        next_action="labor_match_pool_review",
        payload={
            "request_id":   request_id,
            "roles_needed": roles_needed,
            "event_date":   event_date,
            "shift_window": shift_window,
            "location":     location,
            # notes omitted from ledger payload — may contain raw operator remarks
        },
    )

    return templates.TemplateResponse(
        request,
        "submission_success.html",
        context=_ctx(request, {
            "title":        "Dispatch Request Received",
            "summary":      "Your labor request has been logged for dispatch review. "
                            "Matching will run against the available pool.",
            "return_href":  "/labor/matches",
            "return_label": "Back to Match Pool",
            "next_href":    "/labor/match-review",
            "next_label":   "Open Single Match Review",
            "record_id":    request_id,
            "step_number":  1,
            "step_total":   2,
            "step_name":    "Dispatch Request",
            "why_next":     "Your request is now the employer-side target for worker matching.",
        }),
    )


@labor_rail_router.get("/labor/growth-ladder", response_class=HTMLResponse)
def labor_growth_ladder(request: Request):
    log_page_view(request, rail="labor", event_type="growth_ladder_viewed",
                  title="Worker Growth Ladder viewed",
                  next_action="labor_intake_opened")
    return templates.TemplateResponse(
        request, "labor_growth_ladder.html", context=_ctx(request)
    )


@labor_rail_router.get("/labor/readiness", response_class=HTMLResponse)
def labor_readiness(request: Request, worker_id: str = Query("")):
    breakdown = get_worker_readiness_breakdown(worker_id or None)
    log_page_view(request, rail="labor", event_type="readiness_dashboard_viewed",
                  title="Readiness score dashboard viewed",
                  next_action="labor_profile_edit_opened")
    return templates.TemplateResponse(
        request,
        "labor_readiness.html",
        context=_ctx(request, {"breakdown": breakdown}),
    )


@labor_rail_router.get("/labor/dispatch-directory", response_class=HTMLResponse)
def labor_dispatch_directory(
    request: Request,
    city: str   = Query(""),
    status: str = Query(""),
):
    companies = get_dispatch_companies(city_filter=city, status_filter=status)
    log_page_view(request, rail="labor", event_type="dispatch_directory_viewed",
                  title="Company Dispatch Directory viewed",
                  next_action="dispatch_request_submitted")
    return templates.TemplateResponse(
        request,
        "labor_dispatch_directory.html",
        context=_ctx(request, {
            "companies":     companies,
            "total":         len(companies),
            "city_filter":   city,
            "status_filter": status,
        }),
    )


@labor_rail_router.post("/labor/contact-request", response_class=HTMLResponse)
async def labor_contact_request(
    request: Request,
    requester_role: str = Form(""),
    target_display_id: str = Form(""),
    request_context: str = Form(""),
):
    """
    Anti-contact-exposure endpoint.
    Logs the intent to connect but NEVER returns contact details of either party.
    All contact is mediated through platform dispatch.
    """
    from uuid import uuid4 as _uuid4
    contact_req_id = f"cr_{_uuid4().hex[:10]}"

    write_event(
        rail="labor",
        event_type="contact_request_initiated",
        title="Contact request initiated — mediated by platform",
        route="/labor/contact-request",
        status="pending_review",
        actor_id=get_actor_id(request),
        actor_type="visitor",
        next_action="dispatch_coordinator_review",
        payload={
            "contact_req_id":   contact_req_id,
            "requester_role":   requester_role,
            "target_display_id": target_display_id,
            # request_context omitted from ledger — may contain raw remarks
        },
    )

    return templates.TemplateResponse(
        request,
        "submission_success.html",
        context=_ctx(request, {
            "title":        "Connection Request Logged",
            "summary":      "Your request has been recorded for dispatch coordinator review. "
                            "Direct contact details are not shared through this interface. "
                            "A coordinator will facilitate contact if the match is approved.",
            "return_href":  "/labor/matches",
            "return_label": "Back to Match Pool",
            "next_href":    "/labor/dispatch-directory",
            "next_label":   "View Dispatch Directory",
            "record_id":    contact_req_id,
            "step_number":  1,
            "step_total":   2,
            "step_name":    "Contact Request",
            "why_next":     "Direct contact is mediated — no phone or email is shared at this stage.",
        }),
    )


@labor_rail_router.get("/labor-rail/access")
def labor_rail_access(request: Request):
    log_page_view(request, rail="labor", event_type="labor_rail_access_viewed",
                  title="Labor Rail access page viewed",
                  next_action="intake_form_opened")
    basic_link = os.getenv("STRIPE_LINK_LABOR_RAIL_BASIC", "").strip()
    pro_link = os.getenv("STRIPE_LINK_LABOR_RAIL_PRO", "").strip()
    return templates.TemplateResponse(
        request,
        "labor_rail_access.html",
        context=_ctx(request, {
            "labor_rail_basic": basic_link,
            "labor_rail_pro": pro_link,
        }),
    )
