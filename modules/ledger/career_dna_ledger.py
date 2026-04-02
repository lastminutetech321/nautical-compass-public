from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

class CareerDNALedger:
    """Worker living record ledger."""

    def __init__(self, path: str = "./runtime/career_dna_ledger.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        worker_id: str,
        event_type: str,
        role: Optional[str] = None,
        company: Optional[str] = None,
        venue: Optional[str] = None,
        market: Optional[str] = None,
        shift_status: Optional[str] = None,
        pay_band: Optional[str] = None,
        verification_source: Optional[str] = None,
        certifications: Optional[List[str]] = None,
        tools_used: Optional[List[str]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "ts": int(time.time()),
            "worker_id": worker_id,
            "event_type": event_type,
            "role": role,
            "company": company,
            "venue": venue,
            "market": market,
            "shift_status": shift_status,
            "pay_band": pay_band,
            "verification_source": verification_source,
            "certifications": certifications or [],
            "tools_used": tools_used or [],
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()[-limit:] if x.strip()]
