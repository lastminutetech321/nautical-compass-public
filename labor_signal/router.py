from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .config import LaborSignalSettings
from .repository import repo
from .schemas import LaborSignalRecord, UserSkillGapRequest
from .services_ingest import ingest_labor_signal, build_region_snapshot
from .services_scoring import score_role_opportunities
from .services_skill_gap import generate_user_skill_gap
from .services_routing import generate_market_route

router = APIRouter(prefix="/modules/labor-signal", tags=["labor-signal"])


@router.get("/health")
def labor_signal_health():
    return JSONResponse(
        {
            "ok": True,
            "module": "labor_signal",
            "flags": {
                "ENABLE_LABOR_SIGNAL_ENGINE": LaborSignalSettings.ENABLE_LABOR_SIGNAL_ENGINE,
                "ENABLE_OPPORTUNITY_SCORING": LaborSignalSettings.ENABLE_OPPORTUNITY_SCORING,
                "ENABLE_SKILL_GAP_ENGINE": LaborSignalSettings.ENABLE_SKILL_GAP_ENGINE,
                "ENABLE_MARKET_ROUTING_ADVISORY": LaborSignalSettings.ENABLE_MARKET_ROUTING_ADVISORY,
                "SHOW_LABOR_WIDGETS_TO_USERS": LaborSignalSettings.SHOW_LABOR_WIDGETS_TO_USERS,
                "SHOW_LABOR_WIDGETS_TO_ADMIN": LaborSignalSettings.SHOW_LABOR_WIDGETS_TO_ADMIN,
                "USE_SIGNAL_ENGINE_IN_MATCHING": LaborSignalSettings.USE_SIGNAL_ENGINE_IN_MATCHING,
            },
            "record_counts": {
                "signal_records": len(repo.signal_records),
                "region_snapshots": len(repo.region_snapshots),
                "role_scores": len(repo.role_scores),
                "skill_gap_reports": len(repo.skill_gap_reports),
                "route_decisions": len(repo.route_decisions),
            },
        }
    )


@router.post("/ingest")
def labor_signal_ingest(payload: LaborSignalRecord):
    record = ingest_labor_signal(payload)
    return {"ok": True, "record": record}


@router.post("/snapshot/{region_code}")
def labor_signal_snapshot(region_code: str):
    snapshot = build_region_snapshot(region_code, LaborSignalSettings.DEFAULT_REGION_NAME)
    return {"ok": True, "snapshot": snapshot}


@router.get("/snapshot/{region_code}")
def labor_signal_snapshot_get(region_code: str):
    snapshot = repo.get_latest_region_snapshot(region_code)
    return {"ok": True, "snapshot": snapshot}


@router.post("/score/{region_code}")
def labor_signal_score(region_code: str):
    scores = score_role_opportunities(region_code)
    return {"ok": True, "scores": scores}


@router.post("/skill-gap")
def labor_signal_skill_gap(payload: UserSkillGapRequest):
    report = generate_user_skill_gap(payload)
    return {"ok": True, "report": report}


@router.post("/route")
def labor_signal_route(payload: UserSkillGapRequest):
    decision = generate_market_route(payload)
    return {"ok": True, "decision": decision}
