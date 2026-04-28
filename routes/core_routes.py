from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from services.intake_service import complete_intake
from services.results_service import build_results_summary
from services.document_service import generate_w9
from services.helm_service import get_helm_state


core_routes = APIRouter()


class IntakeCompleteRequest(BaseModel):
    userId: str
    intakeState: Dict[str, Any]


class ResultsSummaryRequest(BaseModel):
    intakeState: Dict[str, Any]


class GenerateW9Request(BaseModel):
    userId: str
    intakeState: Dict[str, Any]


class HelmStateRequest(BaseModel):
    intakeState: Dict[str, Any]
    scores: Optional[Dict[str, Any]] = {}
    routes: Optional[Dict[str, Any]] = {}
    history: Optional[List[Dict[str, Any]]] = []


@core_routes.post("/api/intake/complete")
def post_complete_intake(payload: IntakeCompleteRequest):
    try:
        result = complete_intake(payload.userId, payload.intakeState)
        return {"ok": True, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@core_routes.post("/api/results/summary")
def post_results_summary(payload: ResultsSummaryRequest):
    try:
        result = build_results_summary(payload.intakeState)
        return {"ok": True, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@core_routes.post("/api/documents/generate-w9")
def post_generate_w9(payload: GenerateW9Request):
    try:
        result = generate_w9(payload.userId, payload.intakeState)
        return {"ok": True, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@core_routes.post("/api/helm/state")
def post_helm_state(payload: HelmStateRequest):
    try:
        result = get_helm_state(
            intake_state=payload.intakeState,
            scores=payload.scores or {},
            routes=payload.routes or {},
            document_history=payload.history or [],
        )
        return {"ok": True, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
