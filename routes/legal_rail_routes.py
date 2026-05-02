from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional

from services.standing_analysis_service import analyze_standing, StandingAnalysisServiceError
from services.capacity_analysis_service import analyze_capacity, CapacityAnalysisServiceError
from services.rights_violation_service import analyze_rights_violations, RightsViolationServiceError
from services.regulatory_routing_service import analyze_regulatory_routes, RegulatoryRoutingServiceError
from services.jurisdiction_service import analyze_jurisdiction, JurisdictionServiceError
from services.legal_results_service import build_legal_results, LegalResultsServiceError
from services.case_builder_service import build_case_packet, CaseBuilderServiceError

legal_rail_router = APIRouter()


class LegalAnalysisRequest(BaseModel):
    intakeState: Dict[str, Any]
    complaintId: Optional[str] = None


class CasePacketRequest(BaseModel):
    userId: str
    intakeState: Dict[str, Any]
    complaintId: str


@legal_rail_router.post("/api/legal/standing")
def post_standing_analysis(payload: LegalAnalysisRequest):
    try:
        result = analyze_standing(payload.intakeState, payload.complaintId)
        return {"ok": True, "data": result}
    except StandingAnalysisServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@legal_rail_router.post("/api/legal/capacity")
def post_capacity_analysis(payload: LegalAnalysisRequest):
    try:
        result = analyze_capacity(payload.intakeState, payload.complaintId)
        return {"ok": True, "data": result}
    except CapacityAnalysisServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@legal_rail_router.post("/api/legal/rights")
def post_rights_analysis(payload: LegalAnalysisRequest):
    try:
        result = analyze_rights_violations(payload.intakeState, payload.complaintId)
        return {"ok": True, "data": result}
    except RightsViolationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@legal_rail_router.post("/api/legal/regulatory-routes")
def post_regulatory_routes(payload: LegalAnalysisRequest):
    try:
        result = analyze_regulatory_routes(payload.intakeState, payload.complaintId)
        return {"ok": True, "data": result}
    except RegulatoryRoutingServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@legal_rail_router.post("/api/legal/jurisdiction")
def post_jurisdiction_analysis(payload: LegalAnalysisRequest):
    try:
        result = analyze_jurisdiction(payload.intakeState, payload.complaintId)
        return {"ok": True, "data": result}
    except JurisdictionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@legal_rail_router.post("/api/legal/results")
def post_legal_results(payload: LegalAnalysisRequest):
    try:
        result = build_legal_results(payload.intakeState, payload.complaintId)
        return {"ok": True, "data": result}
    except LegalResultsServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@legal_rail_router.post("/api/legal/case-packet")
def post_case_packet(payload: CasePacketRequest):
    try:
        result = build_case_packet(payload.userId, payload.intakeState, payload.complaintId)
        return {"ok": True, "data": result}
    except CaseBuilderServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
