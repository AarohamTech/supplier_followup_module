"""The supplier portal and the staff views show the same lines and quantities.

Client feedback: "Inward quantity must be same — on admin it shows 1 qty but on
supplier side it shows 2". The supplier PO detail did not drop delisted lines
(closed / fully received on the CRM side) while every staff view did, and each
view read a different quantity column. Now one helper (services.po_quantities)
defines ordered / inward / pending, and every view uses the same line set.

Uses the in-memory SQLite pattern: call functions directly, prod untouched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_po_qty_consistency.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import ProcurementRecord, SupplierMaster  # noqa: E402,F401
from app.routers import employee_portal, portal  # noqa: E402
from app.services import po_followup_service, po_view_service, user_service  # noqa: E402
from app.services.po_quantities import line_quantities  # noqa: E402


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


SUP = "SSV TECH"
REF = "2627-017291"


def _rec(db, *, po, crm, material, qty=None, po_qty=None, grn=None, pend=None, delisted=False):
    rec = ProcurementRecord(
        crm_no=crm, supplier_po_no=po, material_name=material, supplier_name=SUP,
        po_short_ref=REF, owner_emp_code="E1", signal="BLACK", po_status="APPROVED",
        qty=qty, po_qty=po_qty, grn_qty=grn, pending_qty=pend,
        delisted_at=datetime(2026, 11, 1) if delisted else None,
    )
    db.add(rec)
    return rec


def _key(m) -> tuple:
    get = (lambda k: m.get(k)) if isinstance(m, dict) else (lambda k: getattr(m, k))
    return (get("procurement_record_id"), get("ordered_qty"), get("inward_qty"), get("pending_qty"))


class LineQuantitiesTests(unittest.TestCase):
    def test_feed_quantities_win(self):
        r = ProcurementRecord(qty=2, po_qty=1, grn_qty=1, pending_qty=0)
        self.assertEqual(line_quantities(r), {"ordered_qty": 1.0, "inward_qty": 1.0, "pending_qty": 0.0})

    def test_falls_back_to_desk_qty(self):
        r = ProcurementRecord(qty=2)
        self.assertEqual(line_quantities(r), {"ordered_qty": 2.0, "inward_qty": None, "pending_qty": 2.0})

    def test_pending_derived_from_inward(self):
        r = ProcurementRecord(po_qty=5, grn_qty=2)
        self.assertEqual(line_quantities(r)["pending_qty"], 3.0)
        over = ProcurementRecord(po_qty=5, grn_qty=7)
        self.assertEqual(line_quantities(over)["pending_qty"], 0.0)


class PortalMatchesStaffTests(unittest.TestCase):
    def _seed(self, db):
        sup = SupplierMaster(supplier_name=SUP, is_active=True)
        db.add(sup)
        db.flush()
        # One vendor PO (REF) spread over two recycled counters, with the same
        # material duplicated on both counters, plus a delisted (received) line.
        _rec(db, po="002180", crm="2627-018961", material="WF09-40 SSVT MAKE",
             qty=2, po_qty=1, grn=0, pend=1)
        _rec(db, po="002180", crm="2627-018962", material="WF09-0654 SSVT MAKE",
             qty=2, delisted=True)
        _rec(db, po="002181", crm="2627-018963", material="WF09-40 SSVT MAKE",
             qty=3, po_qty=3, grn=1)
        db.commit()
        user = user_service.create_user(
            db, email="s@ssv.com", password="x" * 8, role=Role.SUPPLIER, supplier_id=sup.id,
        )
        emp = user_service.create_user(
            db, email="e1@employee.local", password="pw", full_name="Owner",
            role="employee", emp_code="E1", username="DESK1",
        )
        return user, emp

    def test_portal_staff_and_employee_payloads_agree_per_counter(self):
        with _temp_db() as db:
            user, emp = self._seed(db)
            for counter in ("002180", "002181"):
                portal_rows = portal.po_materials(counter, user=user, db=db)
                staff = po_view_service.po_detail(db, supplier_po_no=counter, supplier_name=SUP)
                emp_rows = employee_portal.po_materials(counter, supplier_name=SUP, user=emp, db=db)
                p = sorted(_key(m) for m in portal_rows)
                self.assertEqual(p, sorted(_key(m) for m in staff["materials"]), counter)
                self.assertEqual(p, sorted(_key(m) for m in emp_rows), counter)

            # The delisted (received) line is gone on both sides: 1 line, qty 1.
            rows = portal.po_materials("002180", user=user, db=db)
            self.assertEqual([m.material_name for m in rows], ["WF09-40 SSVT MAKE"])
            self.assertEqual((rows[0].ordered_qty, rows[0].inward_qty, rows[0].pending_qty), (1.0, 0.0, 1.0))

    def test_hub_group_lists_each_counter_line_without_summing(self):
        with _temp_db() as db:
            user, _ = self._seed(db)
            records = [
                r for r in db.query(ProcurementRecord).all() if r.delisted_at is None
            ]
            group = po_followup_service.build_po_group_payload(db, records, SUP, "002180")
            hub = sorted(_key(m) for m in group["materials"])
            portal_all = sorted(
                _key(m)
                for counter in ("002180", "002181")
                for m in portal.po_materials(counter, user=user, db=db)
            )
            # Duplicate material across counters stays two lines with their own
            # quantities, matching the portal line for line.
            self.assertEqual(hub, portal_all)
            self.assertEqual(len(hub), 2)
            # Legacy "po_qty" key (mail templates) carries the ordered quantity.
            self.assertTrue(all(m["po_qty"] == m["ordered_qty"] for m in group["materials"]))


if __name__ == "__main__":
    unittest.main()
