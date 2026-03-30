"""
Stripe integration for Financial Engine.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests


class StripeIntegration:
    """Handles Stripe-related integration calls."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 20,
    ) -> None:
        self.api_key = api_key or os.getenv("STRIPE_SECRET_KEY", "")
        self.base_url = (base_url or os.getenv("STRIPE_API_BASE_URL", "https://api.stripe.com/v1")).rstrip("/")
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def healthcheck(self) -> Dict[str, Any]:
        return {
            "provider": "stripe",
            "configured": self.is_configured(),
            "base_url": self.base_url,
        }
