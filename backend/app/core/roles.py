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
    # External supplier portal account. Deliberately OUTSIDE the staff ladder
    # (rank 0) so it never satisfies any staff guard; account type is decided by
    # User.supplier_id, this string just labels the row. See core/deps.py.
    SUPPLIER = "supplier"


# Ordered low → high. Order matters for UI dropdowns and ranking. This is the
# *staff* ladder only — `supplier` is intentionally excluded so admin user
# dropdowns and `require_role` comparisons stay unchanged.
ALL_ROLES: tuple[str, ...] = (Role.VIEWER, Role.USER, Role.MANAGER, Role.ADMIN)

# Every role string the system recognises (staff ladder + the supplier label).
KNOWN_ROLES: tuple[str, ...] = ALL_ROLES + (Role.SUPPLIER,)

DEFAULT_ROLE = Role.VIEWER

# Staff roles rank 1..4; supplier ranks 0 (below viewer) so role_at_least never
# admits a supplier to a staff-gated endpoint.
_RANK: dict[str, int] = {role: idx + 1 for idx, role in enumerate(ALL_ROLES)}
_RANK[Role.SUPPLIER] = 0


def is_valid_role(role: str | None) -> bool:
    return role in KNOWN_ROLES


def normalize_role(role: str | None) -> str:
    """Coerce arbitrary input to a known role, defaulting to the lowest staff role.

    Known roles (incl. `supplier`) round-trip unchanged; anything unrecognised
    falls back to the default so a typo can never silently grant access.
    """
    if role is None:
        return DEFAULT_ROLE
    candidate = role.strip().lower()
    return candidate if candidate in KNOWN_ROLES else DEFAULT_ROLE


def rank(role: str | None) -> int:
    return _RANK.get(normalize_role(role), 0)


def role_at_least(role: str | None, minimum: str) -> bool:
    """True if `role` is `minimum` or more privileged."""
    return rank(role) >= rank(minimum)
