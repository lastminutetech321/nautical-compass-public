from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Any, Dict

from services.intake_service import save_field, save_section, complete_intake
from services.complaint_service import get_complaint_summary, add_complaint, build_complaint_packet
from services.standing_analysis_service import analyze_standing
from services.capacity_analysis_service import analyze_capacity
from services.results_service import build_results_summary

router = APIRouter(prefix="/api/intake", tags=["Intake Engine"])

INTAKE_STATE: Dict[str, Any] = {}


class FieldPayload(BaseModel):
    section: str
    field: str
    value: Any


class SectionPayload(BaseModel):
    section: str
    data: Dict[str, Any]


class ComplaintPayload(BaseModel):
    complaint: Dict[str, Any]


@router.get("/state")
def get_state():
    return {"status": "alive", "intake_state": INTAKE_STATE}


@router.post("/field")
def save_intake_field(payload: FieldPayload):
    save_field(INTAKE_STATE, payload.section, payload.field, payload.value)
    return {"status": "saved", "intake_state": INTAKE_STATE}


@router.post("/section")
def save_intake_section(payload: SectionPayload):
    save_section(INTAKE_STATE, payload.section, payload.data)
    return {"status": "saved", "intake_state": INTAKE_STATE}


@router.post("/complaint")
def add_intake_complaint(payload: ComplaintPayload):
    result = add_complaint(INTAKE_STATE, payload.complaint)
    return {"status": "complaint_added", "result": result, "intake_state": INTAKE_STATE}


@router.post("/complete")
def complete_intake_flow():
    completed = complete_intake(INTAKE_STATE)
    complaint_summary = get_complaint_summary(INTAKE_STATE)
    standing = analyze_standing(INTAKE_STATE)
    capacity = analyze_capacity(INTAKE_STATE)
    complaint_packet = build_complaint_packet(INTAKE_STATE)
    results = build_results_summary(INTAKE_STATE)

    return {
        "status": "complete",
        "completed": completed,
        "complaint_summary": complaint_summary,
        "standing": standing,
        "capacity": capacity,
        "complaint_packet": complaint_packet,
        "results": results,
    }
