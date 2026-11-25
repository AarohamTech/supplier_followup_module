"""What a non-admin staff account may see — the single source of truth.

Client rule (2026-11-25): only ``admin`` sees every PO. Staff with role
``manager`` / ``user`` / ``viewer`` see only their own data:

  * POs they own (``ProcurementRecord.owner_emp_code == user.emp_code``), and
  * every PO of a supplier assigned to them on the Supplier Assignment page.

Suppliers, supplier mails, follow-ups, ASNs and mail logs follow from that PO
set. The CRM PO counter is recycled across suppliers, so PO scope is always a
``(UPPER(supplier_name), supplier_po_no)`` pair, never a bare counter.

``for_user`` returns ``None`` for admins (= no filter). Callers do
``if scope is not None: stmt = stmt.where(...)``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Iterable, Optional

from fastapi import Depends
from sqlalchemy import false, func, or_, select, tuple_
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..database import get_db
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.supplier_assignment import SupplierAssignment
from ..models.user import User
from .task_visibility import is_task_admin


def _norm(name: Optional[str]) -> str:
    return (name or "").strip().upper()


@dataclass(frozen=True)
class StaffScope:
    user_id: int
    emp_code: Optional[str]
    # Suppliers assigned to the user (Supplier Assignment page).
    assigned_supplier_ids: frozenset[int]
    assigned_names: frozenset[str]  # UPPER(supplier_name)
    # Derived: every (UPPER(supplier_name), supplier_po_no) the user may see.
    pairs: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    # Derived: every UPPER(supplier_name) the user may see (owned POs + assigned).
    supplier_names: frozenset[str] = field(default_factory=frozenset)

    @property
    def po_counters(self) -> frozenset[str]:
        return frozenset(po for _, po in self.pairs)

    # ── SQL clauses ─────────────────────────────────────────────────────────
    def record_clause(self, R=ProcurementRecord):
        """Filter for ProcurementRecord-like rows (owner_emp_code + supplier_name)."""
        conds = []
        if self.emp_code:
            conds.append(R.owner_emp_code == self.emp_code)
        if self.assigned_names:
            conds.append(func.upper(func.trim(R.supplier_name)).in_(sorted(self.assigned_names)))
        return or_(*conds) if conds else false()

    def pair_clause(self, name_col, po_col):
        """Filter rows carrying (supplier_name, supplier_po_no) columns. Rows of an
        assigned supplier match on the name alone; rows with no supplier name
        match on the bare counter (legacy data that can't be pair-matched)."""
        conds = []
        if self.pairs:
            conds.append(tuple_(func.upper(func.trim(name_col)), po_col).in_(sorted(self.pairs)))
            conds.append(name_col.is_(None) & po_col.in_(sorted(self.po_counters)))
        if self.assigned_names:
            conds.append(func.upper(func.trim(name_col)).in_(sorted(self.assigned_names)))
        return or_(*conds) if conds else false()

    def supplier_name_clause(self, name_col):
        if not self.supplier_names:
            return false()
        return func.upper(func.trim(name_col)).in_(sorted(self.supplier_names))

    def supplier_clause(self, id_col, name_col):
        """Rows keyed by supplier id and/or name (suppliers, ASNs, mail logs)."""
        conds = [self.supplier_name_clause(name_col)]
        if self.assigned_supplier_ids:
            conds.append(id_col.in_(sorted(self.assigned_supplier_ids)))
        return or_(*conds)

    # ── Python checks ───────────────────────────────────────────────────────
    def allows_pair(self, supplier_name: Optional[str], supplier_po_no: Optional[str]) -> bool:
        name = _norm(supplier_name)
        if name and name in self.assigned_names:
            return True
        if not supplier_po_no:
            return False
        if name:
            return (name, supplier_po_no) in self.pairs
        return supplier_po_no in self.po_counters

    def allows_supplier(self, supplier_name: Optional[str] = None, supplier_id: Optional[int] = None) -> bool:
        if supplier_id is not None and supplier_id in self.assigned_supplier_ids:
            return True
        return bool(_norm(supplier_name)) and _norm(supplier_name) in self.supplier_names

    def allows_record(self, rec: Optional[ProcurementRecord]) -> bool:
        if rec is None:
            return False
        if self.emp_code and rec.owner_emp_code == self.emp_code:
            return True
        return self.allows_pair(rec.supplier_name, rec.supplier_po_no)


def is_unscoped(user: Optional[User]) -> bool:
    """Admins see everything."""
    return is_task_admin(user)


def for_user(db: Session, user: User) -> Optional[StaffScope]:
    """The user's scope, or None for an admin (no filter)."""
    if is_unscoped(user):
        return None
    assigned = db.execute(
        select(SupplierMaster.id, SupplierMaster.supplier_name)
        .join(SupplierAssignment, SupplierAssignment.supplier_id == SupplierMaster.id)
        .where(SupplierAssignment.user_id == user.id)
    ).all()
    ids = frozenset(int(i) for i, _ in assigned)
    names = frozenset(_norm(n) for _, n in assigned if _norm(n))
    base = StaffScope(
        user_id=user.id, emp_code=user.emp_code or None,
        assigned_supplier_ids=ids, assigned_names=names,
    )
    R = ProcurementRecord
    rows = db.execute(
        select(R.supplier_name, R.supplier_po_no).where(base.record_clause(R)).distinct()
    ).all()
    pairs = frozenset((_norm(n), po) for n, po in rows if _norm(n) and po)
    supplier_names = frozenset({_norm(n) for n, _ in rows if _norm(n)} | names)
    return StaffScope(
        user_id=base.user_id, emp_code=base.emp_code,
        assigned_supplier_ids=ids, assigned_names=names,
        pairs=pairs, supplier_names=supplier_names,
    )


def get_staff_scope(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Optional[StaffScope]:
    """FastAPI dependency: the caller's StaffScope (None = admin, sees all)."""
    return for_user(db, user)


# Use as ``scope: StaffScopeDep = None``: FastAPI injects the scope, while a
# direct Python call (tests, eportal wrappers) gets None = no filter.
StaffScopeDep = Annotated[Optional[StaffScope], Depends(get_staff_scope)]


def filter_items(scope: Optional[StaffScope], items: Iterable, *, name_attr="supplier_name", po_attr="supplier_po_no") -> list:
    """Post-filter objects/dicts carrying a supplier name + PO counter."""
    items = list(items)
    if scope is None:
        return items

    def get(obj, attr):
        return obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)

    return [it for it in items if scope.allows_pair(get(it, name_attr), get(it, po_attr))]
