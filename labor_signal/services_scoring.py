from __future__ import annotations

from .repository import repo


ROLE_BASELINES = {
    "Registered Nurses": {"wage": 78, "growth": 75, "employment": 80, "transferability": 72, "friction": 68},
    "Computer Systems Engineers/Architects": {"wage": 88, "growth": 82, "employment": 72, "transferability": 84, "friction": 64},
    "General and Operations Managers": {"wage": 84, "growth": 72, "employment": 76, "transferability": 86, "friction": 58},
    "Software Developers": {"wage": 90, "growth": 86, "employment": 74, "transferability": 88, "friction": 60},
    "Managers, All Other": {"wage": 76, "growth": 68, "employment": 70, "transferability": 74, "friction": 52},
    "Business Operations Specialists, All Other": {"wage": 74, "growth": 70, "employment": 78, "transferability": 82, "friction": 44},
    "Lawyers": {"wage": 92, "growth": 60, "employment": 70, "transferability": 60, "friction": 86},
    "Management Analysts": {"wage": 80, "growth": 78, "employment": 72, "transferability": 84, "friction": 54},
}


def _normalize_demand(metric_value: float) -> float:
    if metric_value <= 0:
        return 0
    if metric_value >= 1500:
        return 95
    return round((metric_value / 1500) * 95, 2)


def score_role_opportunities(region_code: str) -> list[dict]:
    records = repo.list_signal_records(region_code=region_code)
    occupation_rows = [r for r in records if r.get("entity_type") == "occupation"]

    scores = []
    for row in occupation_rows:
        role_name = row["entity_name"]
        demand_score = _normalize_demand(float(row.get("metric_value", 0)))
        baseline = ROLE_BASELINES.get(
            role_name,
            {"wage": 60, "growth": 55, "employment": 58, "transferability": 62, "friction": 45},
        )

        wage_score = baseline["wage"]
        growth_score = baseline["growth"]
        employment_volume_score = baseline["employment"]
        transferability_score = baseline["transferability"]
        entry_friction_score = baseline["friction"]

        overall = (
            (demand_score * 0.30)
            + (wage_score * 0.20)
            + (growth_score * 0.20)
            + (employment_volume_score * 0.10)
            + (transferability_score * 0.10)
            - (entry_friction_score * 0.10)
        )

        scores.append(
            {
                "region_code": region_code,
                "role_name": role_name,
                "demand_score": round(demand_score, 2),
                "wage_score": wage_score,
                "growth_score": growth_score,
                "employment_volume_score": employment_volume_score,
                "transferability_score": transferability_score,
                "entry_friction_score": entry_friction_score,
                "overall_opportunity_score": round(overall, 2),
                "recommended_for_fast_entry": entry_friction_score <= 50 and demand_score >= 50,
                "recommended_for_upskill": entry_friction_score > 50 and overall >= 60,
                "recommended_for_pivot": transferability_score >= 75,
            }
        )

    scores = sorted(scores, key=lambda x: x["overall_opportunity_score"], reverse=True)
    repo.save_role_scores(scores)
    return scores
