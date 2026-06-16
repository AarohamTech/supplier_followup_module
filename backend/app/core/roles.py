"""Role definitions and hierarchy — the single source of truth for RBAC.

Four roles, ranked. Each higher role implicitly includes the powers of the
lower ones via `role_at_least()`:

    admin  (4) → everything, including user management
    manager(3) → approve/send mail, escalate, edit settings/automation
    user   (2) → operational work: drafts, tasks, triage, record edits
    viewer (1) → read-only

This module has no framework dependencies so it can be imported anywhere
(models, services, routers, tests) without cycles.
"""
from __future__ import annotations


class Role:
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    VIEWER = "viewer"


# Ordered low → high. Order matters for UI dropdowns and ranking.
ALL_ROLES: tuple[str, ...] = (Role.VIEWER, Role.USER, Role.MANAGER, Role.ADMIN)

DEFAULT_ROLE = Role.VIEWER

_RANK: dict[str, int] = {role: idx + 1 for idx, role in enumerate(ALL_ROLES)}


def is_valid_role(role: str | None) -> bool:
    return role in _RANK


def normalize_role(role: str | None) -> str:
    """Coerce arbitrary input to a known role, defaulting to the lowest."""
    if role is None:
        return DEFAULT_ROLE
    candidate = role.strip().lower()
    return candidate if candidate in _RANK else DEFAULT_ROLE


def rank(role: str | None) -> int:
    return _RANK.get(normalize_role(role), 0)


def role_at_least(role: str | None, minimum: str) -> bool:
    """True if `role` is `minimum` or more privileged."""
    return rank(role) >= rank(minimum)
