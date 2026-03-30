"""
Business account model for Financial Engine.
"""

class BusinessAccount:
    """Represents a connected business account."""

    def __init__(self, business_id: str, provider: str, status: str):
        self.business_id = business_id
        self.provider = provider
        self.status = status

    def to_dict(self) -> dict:
        return {
            "business_id": self.business_id,
            "provider": self.provider,
            "status": self.status,
        }
