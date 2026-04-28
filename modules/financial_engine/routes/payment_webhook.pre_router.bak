"""
Route stub for payment webhook handling.
"""

from __future__ import annotations

from modules.financial_engine.services.payment_service import PaymentService


def payment_webhook(invoice_id: str = "demo-invoice", amount: float = 100.0, provider: str = "stripe") -> dict:
    service = PaymentService()
    return service.record_payment(invoice_id=invoice_id, amount=amount, provider=provider)
