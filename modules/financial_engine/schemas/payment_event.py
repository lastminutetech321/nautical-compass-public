from __future__ import annotations

from typing import Any, Dict, Optional


def build_payment_event(
    *,
    provider: str,
    action: str,
    ok: bool,
    status_code: Optional[int] = None,
    provider_txn_id: Optional[str] = None,
    amount: Optional[float] = None,
    currency: str = "USD",
    direction: Optional[str] = None,
    source_type: Optional[str] = None,
    destination_type: Optional[str] = None,
    invoice_id: Optional[str] = None,
    service_id: Optional[str] = None,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
    labor_order_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "provider": provider,
        "action": action,
        "ok": ok,
        "status_code": status_code,
        "provider_txn_id": provider_txn_id,
        "amount": amount,
        "currency": currency,
        "direction": direction,
        "source_type": source_type,
        "destination_type": destination_type,
        "invoice_id": invoice_id,
        "service_id": service_id,
        "user_id": user_id,
        "case_id": case_id,
        "labor_order_id": labor_order_id,
        "payload": payload or {},
        "data": data or {},
        "raw": raw or {},
    }
