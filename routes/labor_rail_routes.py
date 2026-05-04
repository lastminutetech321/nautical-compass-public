import os
import time
from uuid import uuid4

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.living_ledger import log_page_view, write_event, get_actor_id
from services.labor_matching import (
    get_match_pool,
    get_worker_readiness_breakdown,
    get_dispatch_companies,
    parse_job_request,
    save_job_request,
    load_job_request,
    match_workers_to_job,
    save_dispatch_assignment,
    update_dispatch_assignment,
    get_assignment_status,
    get_existing_assignments,
    load_dispatch_queue,
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


@labor_rail_router.post("/labor/matches/request")
async def labor_matches_request(
    request: Request,
    roles_needed: str = Form(""),
    event_date: str   = Form(""),
    shift_window: str = Form(""),
    location: str     = Form(""),
    notes: str        = Form(""),
):
    job = parse_job_request({
        "roles_needed": roles_needed,
        "event_date":   event_date,
        "shift_window": shift_window,
        "location":     location,
        # notes intentionally excluded from job object
    })

    save_job_request(job)

    write_event(
        rail="labor",
        event_type="dispatch_review_requested",
        title="Dispatch review requested",
        route="/labor/matches/request",
        status="submitted",
        actor_id=get_actor_id(request),
        actor_type="employer",
        next_action="labor_match_results_viewed",
        payload={
            "request_id":    job["request_id"],
            "roles_needed":  roles_needed,
            "event_date":    event_date,
            "shift_window":  shift_window,
            "location":      location,
            "role_keywords": job["role_keywords"],
            # notes omitted — may contain raw operator remarks
        },
    )

    return RedirectResponse(
        url=f"/labor/matches/results/{job['request_id']}",
        status_code=303,
    )


@labor_rail_router.get("/labor/matches/results/{request_id}", response_class=HTMLResponse)
def labor_match_results(request: Request, request_id: str):
    job = load_job_request(request_id)

    if not job:
        return templates.TemplateResponse(
            request,
            "submission_success.html",
            context=_ctx(request, {
                "title":        "Request Not Found",
                "summary":      "No dispatch request was found for this ID. "
                                "It may have expired or the link is incorrect.",
                "return_href":  "/labor/matches",
                "return_label": "Back to Match Pool",
                "next_href":    "/labor/matches",
                "next_label":   "Submit a New Request",
                "record_id":    request_id,
                "step_number":  1,
                "step_total":   1,
                "step_name":    "Request Lookup",
                "why_next":     "Submit a new dispatch request to run matching.",
            }),
        )

    candidates           = match_workers_to_job(job)
    existing_assignments = get_existing_assignments(request_id)

    log_page_view(
        request,
        rail="labor",
        event_type="labor_match_results_viewed",
        title="Match results viewed",
        next_action="contact_request_initiated",
    )

    return templates.TemplateResponse(
        request,
        "labor_match_results.html",
        context=_ctx(request, {
            "job":                job,
            "candidates":         candidates,
            "total":              len(candidates),
            "existing_assignments": existing_assignments,
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
    requester_role:    str = Form(""),
    target_display_id: str = Form(""),
    request_context:   str = Form(""),   # holds job request_id
    worker_role:       str = Form(""),
    worker_market:     str = Form(""),
    match_score:       str = Form("0"),
):
    """
    Anti-contact-exposure endpoint.
    Logs the intent to connect, persists a pending dispatch assignment,
    but NEVER returns contact details of either party.
    """
    contact_req_id = f"cr_{uuid4().hex[:10]}"

    # Persist pending assignment (no PII stored)
    save_dispatch_assignment({
        "contact_req_id": contact_req_id,
        "request_id":     request_context,
        "display_id":     target_display_id,
        "status":         "pending",
        "worker_role":    worker_role,
        "worker_market":  worker_market,
        "match_score":    int(match_score) if match_score.lstrip("-").isdigit() else 0,
    })

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
            "contact_req_id":    contact_req_id,
            "requester_role":    requester_role,
            "target_display_id": target_display_id,
            "request_id":        request_context,
            # worker_role / worker_market omitted from ledger — not needed for audit
            # raw notes never accepted or stored
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
            "return_href":  f"/labor/matches/results/{request_context}" if request_context else "/labor/matches",
            "return_label": "Back to Match Results",
            "next_href":    f"/labor/dispatch/status/{contact_req_id}",
            "next_label":   "Check Request Status",
            "record_id":    contact_req_id,
            "step_number":  1,
            "step_total":   2,
            "step_name":    "Contact Request",
            "why_next":     "Direct contact is mediated — no phone or email is shared at this stage.",
        }),
    )


@labor_rail_router.get("/labor/dispatch/queue", response_class=HTMLResponse)
def labor_dispatch_queue(
    request: Request,
    status: str = Query(""),
):
    # Operator-only surface — no auth guard in Phase 3; document as internal
    queue = load_dispatch_queue(status_filter=status)
    log_page_view(
        request,
        rail="labor",
        event_type="dispatch_queue_viewed",
        title="Dispatch coordinator queue viewed",
        next_action="dispatch_action_taken",
    )
    return templates.TemplateResponse(
        request,
        "labor_dispatch_queue.html",
        context=_ctx(request, {
            "queue":         queue,
            "total":         len(queue),
            "status_filter": status,
        }),
    )


@labor_rail_router.post("/labor/dispatch/action")
async def labor_dispatch_action(
    request: Request,
    contact_req_id: str = Form(""),
    action: str         = Form(""),
):
    # Validate action to prevent injection
    if action not in ("approve", "reject"):
        return RedirectResponse(url="/labor/dispatch/queue", status_code=303)

    new_status = "approved" if action == "approve" else "rejected"
    update_dispatch_assignment(contact_req_id, new_status)

    write_event(
        rail="labor",
        event_type=f"dispatch_{new_status}",
        title=f"Dispatch assignment {new_status}",
        route="/labor/dispatch/action",
        status=new_status,
        actor_id=get_actor_id(request),
        actor_type="coordinator",
        next_action="dispatch_queue_review",
        payload={
            "contact_req_id": contact_req_id,
            "action":         action,
            # no worker contact, no employer contact stored
        },
    )

    return RedirectResponse(url="/labor/dispatch/queue", status_code=303)


@labor_rail_router.get("/labor/dispatch/status/{contact_req_id}", response_class=HTMLResponse)
def labor_dispatch_status(request: Request, contact_req_id: str):
    assignment = get_assignment_status(contact_req_id)
    return templates.TemplateResponse(
        request,
        "labor_dispatch_status.html",
        context=_ctx(request, {
            "contact_req_id": contact_req_id,
            "assignment":     assignment,
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
