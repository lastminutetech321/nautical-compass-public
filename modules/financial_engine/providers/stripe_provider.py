from __future__ import annotations

from typing import Any, Dict

from modules.financial_engine.integrations.stripe import StripeIntegration
from modules.financial_engine.providers.base import PaymentProvider


class StripeProvider(PaymentProvider):
    """NC adapter for Stripe."""

    def __init__(self) -> None:
        self.client = StripeIntegration()

    def is_configured(self) -> bool:
        return self.client.is_configured()

    def healthcheck(self) -> Dict[str, Any]:
        return self.client.healthcheck()

    def create_charge(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = payload.get("path", "payment_intents")
        body = payload.get("body", payload)
        result = self.client.request("post", path, body)
        return {
            "provider": "stripe",
            "action": "create_charge",
            "ok": result.get("ok", False),
            "status_code": result.get("status_code"),
            "data": result.get("data"),
            "raw": result,
        }

    def create_payout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = payload.get("path", "payouts")
        body = payload.get("body", payload)
        result = self.client.request("post", path, body)
        return {
            "provider": "stripe",
            "action": "create_payout",
            "ok": result.get("ok", False),
            "status_code": result.get("status_code"),
            "data": result.get("data"),
            "raw": result,
        }

    def fetch_transaction(self, provider_txn_id: str) -> Dict[str, Any]:
        result = self.client.request("get", f"payment_intents/{provider_txn_id}")
        return {
            "provider": "stripe",
            "action": "fetch_transaction",
            "ok": result.get("ok", False),
            "status_code": result.get("status_code"),
            "data": result.get("data"),
            "raw": result,
        }

    def parse_webhook(self, headers: Dict[str, Any], body: bytes) -> Dict[str, Any]:
        return {
            "provider": "stripe",
            "action": "parse_webhook",
            "ok": True,
            "headers": headers,
            "raw_body": body.decode("utf-8", errors="replace"),
        }
