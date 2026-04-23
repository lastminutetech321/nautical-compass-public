from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

class TransactionLedger:
    """Money and rail memory ledger."""

    def __init__(self, path: str = "./runtime/transaction_ledger.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        provider: str,
        action: str,
        status: str,
        amount: Optional[float] = None,
        currency: str = "USD",
        invoice_id: Optional[str] = None,
        service_id: Optional[str] = None,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
        labor_order_id: Optional[str] = None,
        provider_txn_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "ts": int(time.time()),
            "provider": provider,
            "action": action,
            "status": status,
            "amount": amount,
            "currency": currency,
            "invoice_id": invoice_id,
            "service_id": service_id,
            "user_id": user_id,
            "case_id": case_id,
            "labor_order_id": labor_order_id,
            "provider_txn_id": provider_txn_id,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()[-limit:] if x.strip()]
