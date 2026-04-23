from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

class CompanyRelationLedger:
    """Company-to-worker and company-to-service memory."""

    def __init__(self, path: str = "./runtime/company_relation_ledger.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        company_id: str,
        event_type: str,
        worker_id: Optional[str] = None,
        service_id: Optional[str] = None,
        role: Optional[str] = None,
        outcome: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "ts": int(time.time()),
            "company_id": company_id,
            "event_type": event_type,
            "worker_id": worker_id,
            "service_id": service_id,
            "role": role,
            "outcome": outcome,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()[-limit:] if x.strip()]
