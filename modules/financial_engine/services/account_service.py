"""
Account service for business account connection and status handling.
"""

class AccountService:
    """Handles business account lifecycle logic."""

    def connect_account(self, provider: str, business_id: str) -> dict:
        return {
            "status": "pending",
            "provider": provider,
            "business_id": business_id,
            "message": "Account connection flow initialized."
        }
