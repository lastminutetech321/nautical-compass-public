from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class PaymentProvider(ABC):
    """Normalized NC payment provider contract."""

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_charge(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_payout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_transaction(self, provider_txn_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, headers: Dict[str, Any], body: bytes) -> Dict[str, Any]:
        raise NotImplementedError
