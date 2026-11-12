"""Which PO lines are still OPEN — the one definition every view and the
follow-up cycle share.

Client feedback 2026-11-12: admin pages showed closed POs and the counts
differed between the dashboard, Orders, PO Follow-ups, Black Follow-ups,
workload and the hub, while the employee "My Orders" page was right. My Orders
hid delisted lines; most other places did not filter at all, and the auto
follow-up mail listed (and took its BLACK/RED signal from) closed lines too.

A line is CLOSED when any of these hold:

* ``delisted_at`` is set — the line left the CRM pending desk (received /
  closed / sold on the CRM side). This is what My Orders already used.
* ``receipt_status == COMPLETED`` — the GRN quantities say nothing is left to
  receive (pending qty <= 0). Ingest derives it and leaves it NULL for "Open"
  type POs, whose quantities Hariom IT calls unreliable, so we trust the
  derived status rather than raw ``pending_qty``.
* ``cancellation_status == CANCELLED`` — the cancel was confirmed.
* ``po_status`` is an explicit closed state (CLOSED / COMPLETED / RECEIVED /
  CANCELLED / SHORT CLOSED). DISPATCHED / DELIVERED are the supplier's claim,
  not Hariom's receipt, so those lines stay open until the GRN or the CRM
  closes them.

A line is CHASEABLE (may be followed up with the supplier) when it is open and
no cancellation is pending — chasing a supplier for a PO we are cancelling
would contradict the cancel request.

Python and SQL forms are kept side by side so a list filter and a per-record
check can never drift apart.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import and_, func, not_, or_
from sqlalchemy.sql import ColumnElement

from ..models.procurement import ProcurementRecord

RECEIPT_COMPLETED = "COMPLETED"
CANCEL_CONFIRMED = "CANCELLED"
CANCEL_PENDING = "PENDING"
CLOSED_PO_STATUSES: tuple[str, ...] = (
    "CLOSED",
    "COMPLETED",
    "RECEIVED",
    "CANCELLED",
    "SHORT CLOSED",
    "SHORT CLOSE",
    "SHORTCLOSED",
)
_NOT_CHASED_CANCEL = (CANCEL_PENDING, CANCEL_CONFIRMED)


def _up(value: str | None) -> str:
    return (value or "").strip().upper()


def closed_reason(rec: ProcurementRecord) -> str | None:
    """Why `rec` is closed, or None when it is open."""
    if getattr(rec, "delisted_at", None) is not None:
        return "removed from the CRM pending desk"
    if _up(getattr(rec, "receipt_status", None)) == RECEIPT_COMPLETED:
        return "fully received"
    if _up(getattr(rec, "cancellation_status", None)) == CANCEL_CONFIRMED:
        return "cancelled"
    status = _up(getattr(rec, "po_status", None))
    if status in CLOSED_PO_STATUSES:
        return f"PO status {status}"
    return None


def is_open_line(rec: ProcurementRecord) -> bool:
    return closed_reason(rec) is None


def is_chaseable_line(rec: ProcurementRecord) -> bool:
    """Open, and not waiting on a cancellation — safe to follow up."""
    if not is_open_line(rec):
        return False
    return _up(getattr(rec, "cancellation_status", None)) not in _NOT_CHASED_CANCEL


def open_lines(records: Iterable[ProcurementRecord]) -> list[ProcurementRecord]:
    return [r for r in records if is_open_line(r)]


def chaseable_lines(records: Iterable[ProcurementRecord]) -> list[ProcurementRecord]:
    return [r for r in records if is_chaseable_line(r)]


def open_line_clause(model: type[ProcurementRecord] = ProcurementRecord) -> ColumnElement[bool]:
    """SQL form of :func:`is_open_line` for ``select().where(...)``.

    Every NULL-able column is OR-ed with IS NULL: in SQL ``NULL <> 'X'`` is
    NULL, not true, and would silently drop the (common) NULL rows.
    """
    return and_(
        model.delisted_at.is_(None),
        or_(model.receipt_status.is_(None), func.upper(model.receipt_status) != RECEIPT_COMPLETED),
        or_(
            model.cancellation_status.is_(None),
            func.upper(model.cancellation_status) != CANCEL_CONFIRMED,
        ),
        or_(
            model.po_status.is_(None),
            func.upper(func.trim(model.po_status)).notin_(CLOSED_PO_STATUSES),
        ),
    )


def closed_line_clause(model: type[ProcurementRecord] = ProcurementRecord) -> ColumnElement[bool]:
    return not_(open_line_clause(model))


def chaseable_line_clause(
    model: type[ProcurementRecord] = ProcurementRecord,
) -> ColumnElement[bool]:
    """SQL form of :func:`is_chaseable_line`."""
    return and_(
        open_line_clause(model),
        or_(
            model.cancellation_status.is_(None),
            func.upper(model.cancellation_status).notin_(_NOT_CHASED_CANCEL),
        ),
    )
