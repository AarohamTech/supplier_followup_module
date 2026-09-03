"""Which PO lines a SUPPLIER may see or be mailed about.

The CRM desk feed carries every PO line regardless of approval: ``PoStatus`` is
``APPROVED``, ``NOT APPROVED`` or ``NOT GENERATED``. Staff and employees need the
unapproved lines (to chase approvals internally), but a supplier must never learn
about a PO before it is approved — not in the portal, not in an auto follow-up,
not via the portal assistant.

One predicate, used by every supplier-facing query. It hides only the explicit
"NOT …" states. A NULL status (legacy rows) or any other value (``CONFIRMED`` /
``DISPATCHED`` … written back from supplier replies) stays visible, so a PO does
not vanish from the supplier the moment they reply to it.
"""
from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.sql import ColumnElement

from ..models.procurement import ProcurementRecord

APPROVED = "APPROVED"
_HIDDEN_PREFIX = "NOT "


def is_awaiting_approval(po_status: str | None) -> bool:
    """True for the feed's NOT APPROVED / NOT GENERATED states."""
    return (po_status or "").strip().upper().startswith(_HIDDEN_PREFIX)


def is_supplier_visible(rec: ProcurementRecord) -> bool:
    return not is_awaiting_approval(rec.po_status)


def supplier_visible_clause(model: type[ProcurementRecord] = ProcurementRecord) -> ColumnElement[bool]:
    """SQL form of :func:`is_supplier_visible` for ``select().where(...)``."""
    status = func.upper(func.trim(model.po_status))
    return or_(model.po_status.is_(None), status.notlike(f"{_HIDDEN_PREFIX}%"))
