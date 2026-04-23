from __future__ import annotations

from typing import Any, Dict

from modules.financial_engine.providers.base import PaymentProvider


class BankProviderPlaceholder(PaymentProvider):
    """Placeholder adapter for future bank rails."""

    def __init__(self, provider_name: str = "bank_placeholder") -> None:
        self.provider_name = provider_name

    def is_configured(self) -> bool:
        return False

    def healthcheck(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "configured": False,
            "status": "placeholder",
        }

    def create_charge(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._not_ready("create_charge", payload)

    def create_payout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._not_ready("create_payout", payload)

    def fetch_transaction(self, provider_txn_id: str) -> Dict[str, Any]:
        return self._not_ready("fetch_transaction", {"provider_txn_id": provider_txn_id})

    def parse_webhook(self, headers: Dict[str, Any], body: bytes) -> Dict[str, Any]:
        return self._not_ready(
            "parse_webhook",
            {"headers": headers, "raw_body": body.decode("utf-8", errors="replace")},
        )

    def _not_ready(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "action": action,
            "ok": False,
            "status_code": None,
            "data": {
                "message": f"{self.provider_name} adapter not implemented yet."
            },
            "raw": payload,
        }
