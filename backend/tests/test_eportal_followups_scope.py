"""Scope tests for the employee PO Follow-ups mirrors (/api/eportal/procurement*).

Each employee must only ever see the procurement records they own
(ProcurementRecord.owner_emp_code == user.emp_code) in both the list and the
dashboard KPI counts, and the staff filters (signal, search, pagination) must
work scoped. In-memory SQLite; production data is never touched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_eportal_followups.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    Notification,
    ProcurementRecord,
    SupplierMaster,
    User,
)
from app.routers import employee_portal as ep  # noqa: E402
from app.services import user_service  # noqa: E402


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


def _po(db, *, po, name, owner, signal="RED", crm=None, material="Widget"):
    rec = ProcurementRecord(
        crm_no=crm or f"CRM-{po}", material_name=material, supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _emp(db, emp_code):
    return user_service.create_user(
        db, email=f"{emp_code}@corp.com", password="x" * 8, role=Role.EMPLOYEE,
        emp_code=emp_code, username=emp_code,
    )


class FollowupsScopeTests(unittest.TestCase):
    def _seed(self, db):
        emp1 = _emp(db, "EMP1")
        emp2 = _emp(db, "EMP2")
        # EMP1: 1 BLACK, 1 GREEN.  EMP2: 1 RED.
        _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1", signal="BLACK")
        _po(db, po="PO-A2", name="ACME TOOLS", owner="EMP1", signal="GREEN")
        _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2", signal="RED")
        return emp1, emp2

    def test_list_isolated_between_employees(self):
        with _temp_db() as db:
            emp1, emp2 = self._seed(db)

            l1 = ep.list_procurement(user=emp1, db=db)
            self.assertEqual(l1.total, 2)
            self.assertEqual({r.supplier_po_no for r in l1.items}, {"PO-A1", "PO-A2"})

            l2 = ep.list_procurement(user=emp2, db=db)
            self.assertEqual(l2.total, 1)
            self.assertEqual({r.supplier_po_no for r in l2.items}, {"PO-B1"})

    def test_dashboard_counts_scoped(self):
        with _temp_db() as db:
            emp1, emp2 = self._seed(db)

            d1 = ep.procurement_dashboard(user=emp1, db=db)
            self.assertEqual(d1.total_records, 2)
            self.assertEqual(d1.black_count, 1)
            self.assertEqual(d1.green_count, 1)
            self.assertEqual(d1.red_count, 0)  # EMP2's RED must not leak

            d2 = ep.procurement_dashboard(user=emp2, db=db)
            self.assertEqual(d2.total_records, 1)
            self.assertEqual(d2.black_count, 0)
            self.assertEqual(d2.red_count, 1)

    def test_signal_black_filter_returns_only_own_black(self):
        with _temp_db() as db:
            emp1, emp2 = self._seed(db)
            # Give EMP2 a BLACK too — it must NOT appear for EMP1.
            _po(db, po="PO-B2", name="BETA PARTS", owner="EMP2", signal="BLACK")

            l1 = ep.list_procurement(signal="BLACK", user=emp1, db=db)
            self.assertEqual({r.supplier_po_no for r in l1.items}, {"PO-A1"})
            self.assertEqual(l1.total, 1)

            l2 = ep.list_procurement(signal="BLACK", user=emp2, db=db)
            self.assertEqual({r.supplier_po_no for r in l2.items}, {"PO-B2"})

    def test_search_filter_scoped(self):
        with _temp_db() as db:
            emp1, _ = self._seed(db)
            # Search by PO substring matches only the owner's records.
            l1 = ep.list_procurement(search="PO-A", user=emp1, db=db)
            self.assertEqual({r.supplier_po_no for r in l1.items}, {"PO-A1", "PO-A2"})
            # A term unique to EMP2's PO returns nothing for EMP1.
            l1b = ep.list_procurement(search="PO-B1", user=emp1, db=db)
            self.assertEqual(l1b.items, [])

    def test_pagination_scoped(self):
        with _temp_db() as db:
            emp1, _ = self._seed(db)
            page1 = ep.list_procurement(page=1, size=1, user=emp1, db=db)
            self.assertEqual(page1.total, 2)
            self.assertEqual(len(page1.items), 1)
            page2 = ep.list_procurement(page=2, size=1, user=emp1, db=db)
            self.assertEqual(len(page2.items), 1)
            self.assertNotEqual(
                page1.items[0].supplier_po_no, page2.items[0].supplier_po_no
            )


if __name__ == "__main__":
    unittest.main()
