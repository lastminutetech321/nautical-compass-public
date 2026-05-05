from __future__ import annotations

import os
from typing import Set

from fastapi import Depends, HTTPException, Request

from services.living_ledger import get_actor_id, write_event

ROLE_PERMISSIONS: dict[str, Set[str]] = {
    "worker": set(),
    "coordinator": {
        "view_command_deck",
        "read_operator_settings",
        "view_dispatch_queue",
        "view_labor_readiness",
    },
    "admin": {
        "view_command_deck",
        "read_operator_settings",
        "write_operator_settings",
        "view_dispatch_queue",
        "manage_dispatch_queue",
        "view_labor_readiness",
        "view_company_directory",
        "manage_company_directory",
        "view_event_ledger",
    },
}


def get_operator_role(request: Request) -> str:
    return request.session.get("role", "worker")


def get_operator_perms(request: Request) -> Set[str]:
    return ROLE_PERMISSIONS.get(get_operator_role(request), set())


def require_permission(permission: str):
    """Return a FastAPI Depends that raises 403 if the session role lacks the permission."""
    def _check(request: Request) -> str:
        role = get_operator_role(request)
        if permission not in ROLE_PERMISSIONS.get(role, set()):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return role
    return Depends(_check)


def audit_operator_action(request: Request, action: str, payload: dict) -> None:
    write_event(
        rail="system",
        event_type=f"operator_action_{action}",
        title=f"Operator action: {action}",
        route=str(request.url.path),
        actor_id=get_actor_id(request),
        actor_type=get_operator_role(request),
        payload=payload,
    )
