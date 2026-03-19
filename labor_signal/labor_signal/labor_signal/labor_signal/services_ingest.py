from __future__ import annotations

from datetime import date
from typing import List

from .repository import repo
from .schemas import LaborSignalRecord, RegionSnapshot


def ingest_labor_signal(payload: LaborSignalRecord) -> dict:
    return repo.add_signal_record(payload.model_dump())


def build_region_snapshot(region_code: str, region_name: str) -> dict:
    records = repo.list_signal_records(region_code=region_code)

    unemployment_rate = None
    top_industries: List[str] = []
    top_occupations: List[str] = []

    occupation_rows = []
    industry_rows = []

    for record in records:
        if record.get("metric_name") == "unemployment_rate":
            unemployment_rate = float(record.get("metric_value", 0))

        if record.get("entity_type") == "occupation":
            occupation_rows.append(record)

        if record.get("entity_type") == "industry":
            industry_rows.append(record)

    occupation_rows = sorted(occupation_rows, key=lambda x: x.get("metric_value", 0), reverse=True)
    industry_rows = sorted(industry_rows, key=lambda x: x.get("metric_value", 0), reverse=True)

    top_occupations = [row["entity_name"] for row in occupation_rows[:5]]
    top_industries = [row["entity_name"] for row in industry_rows[:5]]

    score = 0.0
    score += min(len(top_occupations) * 10, 40)
    score += min(len(top_industries) * 8, 32)
    if unemployment_rate is not None:
        score += max(0, 28 - unemployment_rate)

    snapshot = RegionSnapshot(
        region_code=region_code,
        region_name=region_name,
        snapshot_date=str(date.today()),
        unemployment_rate=unemployment_rate,
        top_industries=top_industries,
        top_occupations=top_occupations,
        summary_signal_score=round(score, 2),
    )

    return repo.save_region_snapshot(snapshot.model_dump())
