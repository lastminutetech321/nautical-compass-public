from __future__ import annotations

from .repository import repo
from .schemas import UserSkillGapRequest


ROLE_REQUIREMENTS = {
    "Business Operations Specialist": {
        "skills": {"project coordination", "data analysis", "operations reporting"},
        "certifications": set(),
    },
    "Software Developers": {
        "skills": {"python", "version control", "debugging"},
        "certifications": set(),
    },
    "General and Operations Managers": {
        "skills": {"team leadership", "operations planning", "process improvement"},
        "certifications": set(),
    },
    "Computer Systems Engineers/Architects": {
        "skills": {"systems design", "networking", "cloud fundamentals"},
        "certifications": {"aws", "azure", "security+"},
    },
}


def generate_user_skill_gap(request: UserSkillGapRequest) -> dict:
    req = ROLE_REQUIREMENTS.get(
        request.target_role,
        {"skills": {"communication", "problem solving"}, "certifications": set()},
    )

    current_skills = {skill.strip().lower() for skill in request.skills if skill.strip()}
    current_certs = {cert.strip().lower() for cert in request.certifications if cert.strip()}
    required_skills = {skill.strip().lower() for skill in req["skills"]}
    required_certs = {cert.strip().lower() for cert in req["certifications"]}

    missing_skills = sorted(required_skills - current_skills)
    missing_certs = sorted(required_certs - current_certs)

    matched_skills = len(required_skills.intersection(current_skills))
    matched_certs = len(required_certs.intersection(current_certs))

    total_required = max(len(required_skills) + len(required_certs), 1)
    total_matched = matched_skills + matched_certs
    match_score = round((total_matched / total_required) * 100, 2)

    if match_score >= 80:
        path = "direct_match"
        readiness_days = 7
    elif match_score >= 55:
        path = "upskill_then_route"
        readiness_days = 45
    elif match_score >= 35:
        path = "pivot_role_first"
        readiness_days = 75
    else:
        path = "training_required"
        readiness_days = 120

    training_priority = []
    for skill in missing_skills:
        training_priority.append(f"Build {skill}")
    for cert in missing_certs:
        training_priority.append(f"Add certification: {cert}")

    report = {
        "user_id": request.user_id,
        "target_role": request.target_role,
        "region_code": request.region_code,
        "current_match_score": match_score,
        "missing_skills": missing_skills,
        "missing_certifications": missing_certs,
        "training_priority": training_priority,
        "estimated_readiness_days": readiness_days,
        "recommended_path": path,
    }

    return repo.save_skill_gap_report(report)
