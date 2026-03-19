from typing import List, Optional
from pydantic import BaseModel, Field


class LaborSignalRecord(BaseModel):
    source_name: str
    region_code: str
    region_name: str
    dataset_name: str
    metric_group: str
    metric_name: str
    entity_type: str
    entity_name: str
    entity_code: Optional[str] = None
    metric_value: float
    metric_unit: str
    time_period_label: str
    time_period_start: Optional[str] = None
    time_period_end: Optional[str] = None
    seasonality: Optional[str] = None
    notes: Optional[str] = None


class RegionSnapshot(BaseModel):
    region_code: str
    region_name: str
    snapshot_date: str
    unemployment_rate: Optional[float] = None
    top_industries: List[str] = Field(default_factory=list)
    top_occupations: List[str] = Field(default_factory=list)
    summary_signal_score: float = 0.0


class RoleOpportunityScore(BaseModel):
    region_code: str
    role_name: str
    demand_score: float
    wage_score: float
    growth_score: float
    employment_volume_score: float
    transferability_score: float
    entry_friction_score: float
    overall_opportunity_score: float
    recommended_for_fast_entry: bool
    recommended_for_upskill: bool
    recommended_for_pivot: bool


class UserSkillGapRequest(BaseModel):
    user_id: str
    region_code: str = "DC"
    target_role: str
    current_roles: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)


class UserSkillGapReport(BaseModel):
    user_id: str
    target_role: str
    region_code: str
    current_match_score: float
    missing_skills: List[str] = Field(default_factory=list)
    missing_certifications: List[str] = Field(default_factory=list)
    training_priority: List[str] = Field(default_factory=list)
    estimated_readiness_days: int
    recommended_path: str


class MarketRouteDecision(BaseModel):
    user_id: str
    region_code: str
    recommended_route: str
    primary_role_target: str
    secondary_role_target: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    confidence_score: float
