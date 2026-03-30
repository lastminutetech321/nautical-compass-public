"""
Route stub for creating an invoice.
"""

from __future__ import annotations

from modules.financial_engine.services.invoice_service import InvoiceService


def create_invoice(customer_id: str = "demo-customer", amount: float = 100.0) -> dict:
    service = InvoiceService()
    return service.create_invoice(customer_id=customer_id, amount=amount)
