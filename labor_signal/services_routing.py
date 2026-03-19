from __future__ import annotations

from .repository import repo
from .schemas import UserSkillGapRequest
from .services_skill_gap import generate_user_skill_gap
from .services_scoring import score_role_opportunities


def generate_market_route(request: UserSkillGapRequest) -> dict:
    role_scores = repo.list_role_scores(request.region_code)
    if not role_scores:
        role_scores = score_role_opportunities(request.region_code)

    gap_report = generate_user_skill_gap(request)

    best_role = role_scores[0]["role_name"] if role_scores else request.target_role
    second_role = role_scores[1]["role_name"] if len(role_scores) > 1 else None

    reason_codes = []
    confidence = 50.0

    if gap_report["recommended_path"] == "direct_match":
        route = "direct_match"
        confidence += 25
        reason_codes.append("high_profile_alignment")
    elif gap_report["recommended_path"] == "upskill_then_route":
        route = "upskill_then_route"
        confidence += 15
        reason_codes.append("manageable_skill_gap")
    elif gap_report["recommended_path"] == "pivot_role_first":
        route = "pivot_role_first"
        confidence += 10
        reason_codes.append("adjacent_role_path")
    else:
        route = "training_required"
        reason_codes.append("low_current_alignment")

    if role_scores:
        reason_codes.append("market_demand_signal")
        confidence += min(role_scores[0]["overall_opportunity_score"] / 4, 20)

    decision = {
        "user_id": request.user_id,
        "region_code": request.region_code,
        "recommended_route": route,
        "primary_role_target": best_role,
        "secondary_role_target": second_role,
        "reason_codes": reason_codes,
        "confidence_score": round(min(confidence, 95), 2),
    }

    return repo.save_route_decision(decision)
