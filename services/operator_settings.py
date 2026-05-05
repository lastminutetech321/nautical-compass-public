from __future__ import annotations

_VALID_CERT_STRICTNESS = {"low", "normal", "high"}

_settings: dict = {
    "cert_strictness": "normal",
}


def get_cert_strictness() -> str:
    return _settings["cert_strictness"]


def set_cert_strictness(level: str) -> None:
    if level not in _VALID_CERT_STRICTNESS:
        raise ValueError(f"cert_strictness must be one of {_VALID_CERT_STRICTNESS}")
    _settings["cert_strictness"] = level


def get_all_settings() -> dict:
    return dict(_settings)
