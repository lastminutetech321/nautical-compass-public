"""
Labor / Operator API — /api/labor/*

Endpoints for contractor profile generation, invoice creation,
and operator rail compliance scoring.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
labor_api_router = APIRouter(prefix="/api/labor", tags=["labor-api"])


class ProfileRequest(BaseModel):
    user_id: str
    intake_state: Dict[str, Any]


class InvoiceRequest(BaseModel):
    user_id: str
    intake_state: Dict[str, Any]


class ComplianceScoreRequest(BaseModel):
    operator_type: str
    responses: Dict[str, bool]


@labor_api_router.post("/contractor-profile")
def api_contractor_profile(req: ProfileRequest):
    from services.contractor_profile_service import (
        generate_contractor_profile,
        ContractorProfileServiceError,
    )
    try:
        result = generate_contractor_profile(req.user_id, req.intake_state)
        return JSONResponse({"ok": True, "data": result})
    except ContractorProfileServiceError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("contractor profile error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@labor_api_router.post("/invoice")
def api_invoice(req: InvoiceRequest):
    from services.invoice_service import generate_invoice_payload, InvoiceServiceError
    try:
        result = generate_invoice_payload(req.user_id, req.intake_state)
        return JSONResponse({"ok": True, "data": result})
    except InvoiceServiceError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("invoice error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@labor_api_router.post("/compliance-score")
def api_compliance_score(req: ComplianceScoreRequest):
    from services.compliance_checklist_service import (
        get_checklist_items,
        score_checklist,
    )
    items = get_checklist_items(req.operator_type)
    result = score_checklist(req.responses, req.operator_type)
    return JSONResponse({"ok": True, "data": {**result, "items": items}})


@labor_api_router.get("/compliance-items/{operator_type}")
def api_compliance_items(operator_type: str):
    from services.compliance_checklist_service import get_checklist_items
    items = get_checklist_items(operator_type)
    return JSONResponse({"ok": True, "operator_type": operator_type, "items": items})
