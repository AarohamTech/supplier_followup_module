"""One definition of a PO line's quantities, shared by every view.

Staff views (Orders page, PO detail, employee portal, Communication Hub) and the
supplier portal all read a line's quantities through :func:`line_quantities`,
so the same procurement record shows the same numbers everywhere:

* ``ordered_qty`` — what the PO orders: ``po_qty`` (PoQty from Hariom's
  quantity feed) when synced, else the CRM desk ``qty``.
* ``inward_qty`` — material received (inward / GRN) at Hariom: ``grn_qty``;
  None until the quantity feed has matched the line.
* ``pending_qty`` — still to receive: the feed's ``pending_qty`` when present,
  else ``ordered − inward`` (never below 0), else the ordered quantity (a line on
  the pending desk with no receipt data is wholly pending).

A line's quantities are never summed across rows: a vendor PO spread over
several recycled CRM counters lists each record as its own line.
"""
from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def line_quantities(rec: Any) -> dict[str, float | None]:
    """Ordered / inward / pending quantities for one procurement record."""
    ordered = _num(getattr(rec, "po_qty", None))
    if ordered is None:
        ordered = _num(getattr(rec, "qty", None))
    inward = _num(getattr(rec, "grn_qty", None))
    pending = _num(getattr(rec, "pending_qty", None))
    if pending is None:
        if ordered is not None and inward is not None:
            pending = max(ordered - inward, 0.0)
        else:
            pending = ordered
    return {"ordered_qty": ordered, "inward_qty": inward, "pending_qty": pending}
