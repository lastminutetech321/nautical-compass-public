"""
Payment service for NC provider orchestration.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.financial_engine.providers.bank_provider_placeholder import BankProviderPlaceholder
from modules.financial_engine.providers.mercury_provider import MercuryProvider
from modules.financial_engine.schemas.payment_event import build_payment_event
from modules.financial_engine.schemas.provider_policy import DEFAULT_PROVIDER_POLICY
from modules.financial_engine.providers.stripe_provider import StripeProvider


class PaymentService:
    """NC payment orchestration layer."""

    def __init__(self) -> None:
        self.providers = {
            "stripe": StripeProvider(),
            "mercury": MercuryProvider(),
            "bank_2": BankProviderPlaceholder("bank_2"),
            "bank_3": BankProviderPlaceholder("bank_3"),
        }

    def get_provider(self, provider: str):
        key = (provider or "").strip().lower()
        if key not in self.providers:
            raise ValueError(f"Unsupported payment provider: {provider}")
        return self.providers[key]


    def select_provider(
        self,
        provider: Optional[str] = None,
        *,
        direction: Optional[str] = None,
        amount: Optional[float] = None,
    ) -> str:
        key = (provider or "").strip().lower()
        policy = DEFAULT_PROVIDER_POLICY

        if key:
            if key not in self.providers:
                raise ValueError(f"Unsupported payment provider: {provider}")
            return key

        inbound_default = policy["inbound_default"]
        outbound_default = policy["outbound_default"]
        fallback_provider = policy["fallback_provider"]
        large_transaction_threshold = policy["large_transaction_threshold"]
        large_transaction_preferred = policy["large_transaction_preferred"]

        if direction == "outbound":
            if self.providers[outbound_default].is_configured():
                return outbound_default
            if self.providers[inbound_default].is_configured():
                return inbound_default
            return fallback_provider

        if direction == "inbound":
            if self.providers[inbound_default].is_configured():
                return inbound_default
            if self.providers[outbound_default].is_configured():
                return outbound_default
            return fallback_provider

        if amount is not None and amount >= large_transaction_threshold:
            if self.providers[large_transaction_preferred].is_configured():
                return large_transaction_preferred

        if self.providers[inbound_default].is_configured():
            return inbound_default
        if self.providers[outbound_default].is_configured():
            return outbound_default
        return fallback_provider

    def healthcheck(self) -> Dict[str, Any]:
        return {
            name: client.healthcheck()
            for name, client in self.providers.items()
        }

    def create_charge(self, provider: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        provider = self.select_provider(provider, direction=payload.get('direction', 'inbound'), amount=payload.get('amount'))
        client = self.get_provider(provider)
        result = client.create_charge(payload)
        return self._normalize_result(provider, "create_charge", result, payload)

    def create_payout(self, provider: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        provider = self.select_provider(provider, direction=payload.get('direction', 'outbound'), amount=payload.get('amount'))
        client = self.get_provider(provider)
        result = client.create_payout(payload)
        return self._normalize_result(provider, "create_payout", result, payload)

    def fetch_transaction(self, provider: str, provider_txn_id: str) -> Dict[str, Any]:
        client = self.get_provider(provider)
        result = client.fetch_transaction(provider_txn_id)
        return self._normalize_result(
            provider,
            "fetch_transaction",
            result,
            {"provider_txn_id": provider_txn_id},
        )

    def parse_webhook(
        self,
        provider: str,
        headers: Dict[str, Any],
        body: bytes,
    ) -> Dict[str, Any]:
        client = self.get_provider(provider)
        result = client.parse_webhook(headers, body)
        return self._normalize_result(provider, "parse_webhook", result, {})

    def record_payment(self, invoice_id: str, amount: float, provider: str) -> Dict[str, Any]:
        return {
            "status": "recorded",
            "invoice_id": invoice_id,
            "amount": amount,
            "provider": provider,
            "message": "Payment recorded successfully.",
        }

    def _normalize_result(
        self,
        provider: str,
        action: str,
        result: Dict[str, Any],
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = result.get("data", {})
        provider_txn_id = None

        if isinstance(data, dict):
            provider_txn_id = (
                data.get("id")
                or data.get("transaction_id")
                or data.get("payment_id")
            )

        return build_payment_event(
            provider=provider,
            action=action,
            ok=result.get("ok", False),
            status_code=result.get("status_code"),
            provider_txn_id=provider_txn_id,
            payload=payload or {},
            data=data,
            raw=result.get("raw", result),
        )
