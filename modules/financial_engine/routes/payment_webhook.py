"""
Provider-aware payment webhook routing for NC.
"""

from __future__ import annotations

from typing import Any, Dict

from modules.financial_engine.services.payment_service import PaymentService


def payment_webhook(
    provider: str,
    headers: Dict[str, Any],
    body: bytes,
) -> Dict[str, Any]:
    service = PaymentService()
    return service.parse_webhook(
        provider=provider,
        headers=headers,
        body=body,
    )
