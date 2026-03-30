"""
Mercury integration stub for Financial Engine.
"""

class MercuryIntegration:
    """Handles Mercury-related integration calls."""

    def connect(self) -> dict:
        return {
            "provider": "mercury",
            "status": "ready"
        }
