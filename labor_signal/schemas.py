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


class UserSkillGapRequest(BaseModel):
    user_id: str
    region_code: str = "DC"
    target_role: str
    current_roles: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)
