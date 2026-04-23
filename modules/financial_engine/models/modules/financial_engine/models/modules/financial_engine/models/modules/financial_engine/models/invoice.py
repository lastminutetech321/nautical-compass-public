"""
Invoice model for Financial Engine.
"""

class Invoice:
    """Represents an invoice record."""

    def __init__(self, invoice_id: str, customer_id: str, amount: float, status: str):
        self.invoice_id = invoice_id
        self.customer_id = customer_id
        self.amount = amount
        self.status = status

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "customer_id": self.customer_id,
            "amount": self.amount,
            "status": self.status,
        }
