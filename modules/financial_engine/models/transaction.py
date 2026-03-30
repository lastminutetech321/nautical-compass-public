"""
Transaction model for Financial Engine records.
"""

class Transaction:
    """Represents a financial transaction record."""

    def __init__(self, transaction_id: str, amount: float, status: str):
        self.transaction_id = transaction_id
        self.amount = amount
        self.status = status

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "amount": self.amount,
            "status": self.status,
        }
