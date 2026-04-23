"""
Account service for business account connection and status handling.
"""

from __future__ import annotations

from typing import Dict

from modules.financial_engine.integrations.mercury import MercuryIntegration


class AccountService:
    """Handles business account lifecycle logic."""

    def __init__(self) -> None:
        self.mercury = MercuryIntegration()

    def connect_account(self, provider: str, business_id: str) -> Dict:
        provider_normalized = provider.strip().lower()

        if provider_normalized != "mercury":
            return {
                "ok": False,
                "status": "unsupported_provider",
                "provider": provider,
                "business_id": business_id,
                "message": "Only Mercury is supported in this starter build.",
            }

        mercury_status = self.mercury.connect()

        return {
            "ok": True,
            "status": "pending" if mercury_status["status"] == "ready" else "not_configured",
            "provider": provider_normalized,
            "business_id": business_id,
            "integration": mercury_status,
            "message": "Account connection flow initialized.",
        }
