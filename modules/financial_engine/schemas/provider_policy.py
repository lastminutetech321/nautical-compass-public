from __future__ import annotations

DEFAULT_PROVIDER_POLICY = {
    "inbound_default": "stripe",
    "outbound_default": "mercury",
    "fallback_provider": "bank_2",
    "large_transaction_threshold": 10000,
    "large_transaction_preferred": "mercury",
}
