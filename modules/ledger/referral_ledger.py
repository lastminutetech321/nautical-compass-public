from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

class ReferralLedger:
    """Referral and lineage memory."""

    def __init__(self, path: str = "./runtime/referral_ledger.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        referrer_id: str,
        referred_id: str,
        event_type: str,
        service_id: Optional[str] = None,
        company_id: Optional[str] = None,
        credit_status: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "ts": int(time.time()),
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "event_type": event_type,
            "service_id": service_id,
            "company_id": company_id,
            "credit_status": credit_status,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()[-limit:] if x.strip()]
