from __future__ import annotations

from typing import List, Dict, Any


class InMemoryLaborSignalRepository:
    def __init__(self):
        self.signal_records: List[Dict[str, Any]] = []
        self.region_snapshots: List[Dict[str, Any]] = []
        self.role_scores: List[Dict[str, Any]] = []
        self.skill_gap_reports: List[Dict[str, Any]] = []
        self.route_decisions: List[Dict[str, Any]] = []

    def add_signal_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self.signal_records.append(record)
        return record

    def list_signal_records(self, region_code: str | None = None) -> List[Dict[str, Any]]:
        if not region_code:
            return self.signal_records
        return [r for r in self.signal_records if r.get("region_code") == region_code]

    def save_region_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        self.region_snapshots = [
            s for s in self.region_snapshots
            if not (
                s.get("region_code") == snapshot.get("region_code")
                and s.get("snapshot_date") == snapshot.get("snapshot_date")
            )
        ]
        self.region_snapshots.append(snapshot)
        return snapshot

    def get_latest_region_snapshot(self, region_code: str) -> Dict[str, Any] | None:
        matches = [s for s in self.region_snapshots if s.get("region_code") == region_code]
        if not matches:
            return None
        return matches[-1]

    def save_role_scores(self, scores: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not scores:
            return []
        region_code = scores[0].get("region_code")
        self.role_scores = [s for s in self.role_scores if s.get("region_code") != region_code]
        self.role_scores.extend(scores)
        return scores

    def list_role_scores(self, region_code: str) -> List[Dict[str, Any]]:
        return [s for s in self.role_scores if s.get("region_code") == region_code]

    def save_skill_gap_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        self.skill_gap_reports.append(report)
        return report

    def save_route_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        self.route_decisions.append(decision)
        return decision


repo = InMemoryLaborSignalRepository()
