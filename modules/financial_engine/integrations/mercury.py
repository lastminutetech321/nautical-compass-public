"""
Mercury integration for Financial Engine.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests


class MercuryIntegration:
    """Handles Mercury-related integration calls."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 20,
    ) -> None:
        self.api_key = api_key or os.getenv("MERCURY_API_KEY", "")
        self.base_url = (base_url or os.getenv("MERCURY_API_BASE_URL", "https://api.mercury.com/api/v1")).rstrip("/")
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def healthcheck(self) -> Dict[str, Any]:
        return {
            "provider": "mercury",
            "configured": self.is_configured(),
            "base_url": self.base_url,
        }

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "ok": False,
                "error": "Mercury is not configured. Missing MERCURY_API_KEY or MERCURY_API_BASE_URL.",
            }

        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            content_type = response.headers.get("Content-Type", "")
            body: Any

            if "application/json" in content_type:
                body = response.json()
            else:
                body = response.text

            return {
                "ok": response.ok,
                "status_code": response.status_code,
                "data": body,
            }
        except requests.RequestException as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

    def connect(self) -> Dict[str, Any]:
        return {
            "provider": "mercury",
            "status": "ready" if self.is_configured() else "not_configured",
            "base_url": self.base_url,
        }
