"""
Legal Analysis API — /api/legal/*

All endpoints accept a JSON body with:
  intake_state: dict   — the full intake state object
  complaint_id: str    — optional, defaults to first complaint in profile

Returns structured analysis from the relevant service.
On error returns {"ok": false, "error": "<message>"} with 400/500 status.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
legal_api_router = APIRouter(prefix="/api/legal", tags=["legal-api"])


class LegalAnalysisRequest(BaseModel):
    intake_state: Dict[str, Any]
    complaint_id: Optional[str] = None


def _first_complaint_id(intake_state: dict) -> str | None:
    try:
        complaints = intake_state["complaintProfile"]["complaints"]
        if complaints:
            return complaints[0].get("complaintId")
    except (KeyError, IndexError, TypeError):
        pass
    return None


def _resolve_complaint_id(req: LegalAnalysisRequest) -> str | None:
    if req.complaint_id:
        return req.complaint_id
    return _first_complaint_id(req.intake_state)


@legal_api_router.post("/standing")
def api_standing(req: LegalAnalysisRequest):
    from services.standing_analysis_service import (
        analyze_standing,
        StandingAnalysisServiceError,
    )
    try:
        result = analyze_standing(req.intake_state, _resolve_complaint_id(req))
        return JSONResponse({"ok": True, "data": result})
    except StandingAnalysisServiceError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("standing analysis error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@legal_api_router.post("/capacity")
def api_capacity(req: LegalAnalysisRequest):
    from services.capacity_analysis_service import (
        analyze_capacity,
        CapacityAnalysisServiceError,
    )
    try:
        result = analyze_capacity(req.intake_state, _resolve_complaint_id(req))
        return JSONResponse({"ok": True, "data": result})
    except CapacityAnalysisServiceError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("capacity analysis error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@legal_api_router.post("/rights")
def api_rights(req: LegalAnalysisRequest):
    from services.rights_violation_service import (
        analyze_rights_violations,
        RightsViolationServiceError,
    )
    try:
        result = analyze_rights_violations(req.intake_state, _resolve_complaint_id(req))
        return JSONResponse({"ok": True, "data": result})
    except RightsViolationServiceError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("rights analysis error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@legal_api_router.post("/jurisdiction")
def api_jurisdiction(req: LegalAnalysisRequest):
    from services.jurisdiction_service import analyze_jurisdiction
    try:
        result = analyze_jurisdiction(req.intake_state, _resolve_complaint_id(req))
        return JSONResponse({"ok": True, "data": result})
    except Exception as exc:
        logger.exception("jurisdiction analysis error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@legal_api_router.post("/regulatory-routes")
def api_regulatory(req: LegalAnalysisRequest):
    from services.regulatory_routing_service import analyze_regulatory_routes
    try:
        result = analyze_regulatory_routes(req.intake_state, _resolve_complaint_id(req))
        return JSONResponse({"ok": True, "data": result})
    except Exception as exc:
        logger.exception("regulatory routes error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@legal_api_router.post("/full-analysis")
def api_full_analysis(req: LegalAnalysisRequest):
    """Run all five analyses in one call. Partial failures return the error inline."""
    from services.legal_results_service import build_legal_results
    cid = _resolve_complaint_id(req)
    try:
        result = build_legal_results(req.intake_state, cid)
        return JSONResponse({"ok": True, "data": result})
    except Exception as exc:
        logger.exception("full legal analysis error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
