from __future__ import annotations

import os


class StripeBillingBridge:
    def __init__(self):
        self.basic_link = os.getenv("STRIPE_LINK_LABOR_SIGNAL_BASIC", "").strip()
        self.pro_link = os.getenv("STRIPE_LINK_LABOR_SIGNAL_PRO", "").strip()

    def get_plan_links(self) -> dict:
        return {
            "labor_signal_basic": self.basic_link,
            "labor_signal_pro": self.pro_link,
        }

    def entitlement_status(self, customer_email: str | None = None) -> dict:
        return {
            "connected": bool(self.basic_link or self.pro_link),
            "customer_email": customer_email,
            "module": "labor_signal",
            "status": "bridge_only",
            "note": "Stripe is not fully rewired yet. This bridge preserves the module path without forcing a billing rewrite.",
        }
