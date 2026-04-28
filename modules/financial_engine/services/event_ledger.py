from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class EventLedger:
    """Simple append-only NC event ledger."""

    def __init__(self, path: str = "./runtime/event_ledger.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        event_type: str,
        module: str,
        status: str,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
        labor_order_id: Optional[str] = None,
        provider_expected: Optional[str] = None,
        provider_actual: Optional[str] = None,
        service_id: Optional[str] = None,
        route: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "ts": int(time.time()),
            "event_type": event_type,
            "module": module,
            "status": status,
            "user_id": user_id,
            "case_id": case_id,
            "labor_order_id": labor_order_id,
            "provider_expected": provider_expected,
            "provider_actual": provider_actual,
            "service_id": service_id,
            "route": route,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        out: List[Dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
        return out
