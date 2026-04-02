from __future__ import annotations

from typing import Any, Dict

from modules.financial_engine.integrations.mercury import MercuryIntegration
from modules.financial_engine.providers.base import PaymentProvider


class MercuryProvider(PaymentProvider):
    """NC adapter for Mercury."""

    def __init__(self) -> None:
        self.client = MercuryIntegration()

    def is_configured(self) -> bool:
        return self.client.is_configured()

    def healthcheck(self) -> Dict[str, Any]:
        return self.client.healthcheck()

    def create_charge(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = payload.get("path", "payments")
        body = payload.get("body", payload)
        result = self.client.request("post", path, body)
        return {
            "provider": "mercury",
            "action": "create_charge",
            "ok": result.get("ok", False),
            "status_code": result.get("status_code"),
            "data": result.get("data"),
            "raw": result,
        }

    def create_payout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = payload.get("path", "transactions")
        body = payload.get("body", payload)
        result = self.client.request("post", path, body)
        return {
            "provider": "mercury",
            "action": "create_payout",
            "ok": result.get("ok", False),
            "status_code": result.get("status_code"),
            "data": result.get("data"),
            "raw": result,
        }

    def fetch_transaction(self, provider_txn_id: str) -> Dict[str, Any]:
        result = self.client.request("get", f"transactions/{provider_txn_id}")
        return {
            "provider": "mercury",
            "action": "fetch_transaction",
            "ok": result.get("ok", False),
            "status_code": result.get("status_code"),
            "data": result.get("data"),
            "raw": result,
        }

    def parse_webhook(self, headers: Dict[str, Any], body: bytes) -> Dict[str, Any]:
        return {
            "provider": "mercury",
            "action": "parse_webhook",
            "ok": True,
            "headers": headers,
            "raw_body": body.decode("utf-8", errors="replace"),
        }
