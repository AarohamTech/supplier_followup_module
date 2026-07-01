"""Unit tests for the dashboard breakdown aggregations (signal / supplier / pending).

In-memory SQLite; production data is never touched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import ProcurementRecord  # noqa: E402,F401
from app.services import procurement_breakdown_service as svc  # noqa: E402


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


def _po(db, *, po, name, owner="EMP1", signal="RED", po_status=None):
    db.add(ProcurementRecord(
        crm_no=f"CRM-{po}", material_name="Widget", supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal, po_status=po_status,
    ))
    db.commit()


class BreakdownTests(unittest.TestCase):
    def test_signal_supplier_and_pending_counts(self):
        with _temp_db() as db:
            _po(db, po="A1", name="ACME", signal="GREEN", po_status="OPEN")
            _po(db, po="A2", name="ACME", signal="RED", po_status=None)      # pending (null)
            _po(db, po="B1", name="BETA", signal="RED", po_status="DELIVERED")
            _po(db, po="B2", name="BETA", signal="BLACK", po_status="CLOSED")
            _po(db, po="C1", name="GAMMA", signal="YELLOW", po_status="dispatched")  # case-insensitive

            res = svc.compute_breakdown(db, [])
            self.assertEqual(res["total"], 5)
            self.assertEqual(res["green_count"], 1)
            self.assertEqual(res["yellow_count"], 1)
            self.assertEqual(res["red_count"], 2)
            self.assertEqual(res["black_count"], 1)
            # Pending = not delivered: OPEN + NULL are pending; DELIVERED/CLOSED/dispatched are not.
            self.assertEqual(res["pending_count"], 2)
            by = {s["name"]: s["count"] for s in res["by_supplier"]}
            self.assertEqual(by, {"ACME": 2, "BETA": 2, "GAMMA": 1})

    def test_owner_and_signal_conditions_filter(self):
        with _temp_db() as db:
            _po(db, po="A1", name="ACME", owner="EMP1", signal="RED")
            _po(db, po="A2", name="ACME", owner="EMP1", signal="GREEN")
            _po(db, po="B1", name="BETA", owner="EMP2", signal="RED")

            res = svc.compute_breakdown(db, svc.build_conditions(owner_emp_code="EMP1"))
            self.assertEqual(res["total"], 2)
            self.assertEqual(res["red_count"], 1)
            self.assertEqual({s["name"]: s["count"] for s in res["by_supplier"]}, {"ACME": 2})

            res = svc.compute_breakdown(db, svc.build_conditions(owner_emp_code="EMP1", signal="red"))
            self.assertEqual(res["total"], 1)  # signal upper-cased by build_conditions

    def test_top_suppliers_plus_others(self):
        with _temp_db() as db:
            for i in range(10):  # 10 distinct suppliers → top 8 + Others(2)
                _po(db, po=f"P{i}", name=f"SUP{i:02d}", signal="GREEN")
            res = svc.compute_breakdown(db, [])
            names = [s["name"] for s in res["by_supplier"]]
            self.assertEqual(len(names), 9)
            self.assertEqual(names[-1], "Others")
            self.assertEqual(res["by_supplier"][-1]["count"], 2)


if __name__ == "__main__":
    unittest.main()
