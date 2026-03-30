"""
Route stub for opening a business account.
"""

from __future__ import annotations

from modules.financial_engine.services.account_service import AccountService


def open_account(provider: str = "mercury", business_id: str = "demo-business") -> dict:
    service = AccountService()
    return service.connect_account(provider=provider, business_id=business_id)
