"""Feed delisting, material-wise Orders lines, and material-wise cancellation."""
import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine, true
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ProcurementRecord, User
from app.routers.reports import _pending_po_rows
from app.services import po_cancel_service as pcs
from app.services import po_view_service as pv
from app.services.crm_ingest_service import _sync_delisted


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


def _line(db, *, crm, po="PO1", supplier="Acme", owner=None, material=None, customer=None):
    r = ProcurementRecord(
        crm_no=crm, material_name=material or f"M-{crm}", supplier_po_no=po,
        supplier_name=supplier, owner_emp_code=owner, customer_name=customer,
    )
    db.add(r); db.commit(); db.refresh(r)
    return r


class DelistTests(unittest.TestCase):
    def test_absent_lines_delist_and_reappearing_relist(self):
        with _temp_db() as db:
            a = _line(db, crm="C1"); b = _line(db, crm="C2")
            # Feed only contains C1 -> C2 delists.
            d, rl = _sync_delisted(db, {("C1", "PO1", "M-C1")})
            self.assertEqual((d, rl), (1, 0))
            db.refresh(a); db.refresh(b)
            self.assertIsNone(a.delisted_at)
            self.assertIsNotNone(b.delisted_at)
            # C2 comes back -> relisted.
            d, rl = _sync_delisted(db, {("C1", "PO1", "M-C1"), ("C2", "PO1", "M-C2")})
            self.assertEqual((d, rl), (0, 1))
            db.refresh(b)
            self.assertIsNone(b.delisted_at)

    def test_empty_feed_is_a_noop(self):
        with _temp_db() as db:
            _line(db, crm="C1")
            self.assertEqual(_sync_delisted(db, set()), (0, 0))
            self.assertIsNone(db.query(ProcurementRecord).first().delisted_at)

    def test_delisted_excluded_from_pending_and_grouped_views(self):
        with _temp_db() as db:
            _line(db, crm="C1")
            gone = _line(db, crm="C2", po="PO2")
            _sync_delisted(db, {("C1", "PO1", "M-C1")})
            # workload pending rows
            rows = _pending_po_rows(db, true())
            self.assertEqual([r["supplier_po_no"] for r in rows], ["PO1"])
            # grouped PO view
            items, total = pv.grouped_pos(db)
            self.assertEqual({g["supplier_po_no"] for g in items}, {"PO1"})
            self.assertEqual(total, 1)
            # material lines
            lines, ltotal = pv.material_lines(db)
            self.assertEqual(ltotal, 1)
            self.assertEqual(lines[0]["supplier_po_no"], "PO1")


class MaterialLinesTests(unittest.TestCase):
    def test_owner_filter_and_search(self):
        with _temp_db() as db:
            _line(db, crm="C1", owner="E1", customer="SHRIRAM FOUNDRY")
            _line(db, crm="C2", po="PO2", owner="E2", material="WIDGET-X")
            db.add(User(email="e1@x.com", hashed_password="x", role="employee",
                        emp_code="E1", full_name="Pramod"))
            db.commit()

            lines, total = pv.material_lines(db, owner_emp_code="E1")
            self.assertEqual(total, 1)
            self.assertEqual(lines[0]["owner_emp_code"], "E1")
            self.assertEqual(lines[0]["customer_name"], "SHRIRAM FOUNDRY")

            found, ftotal = pv.material_lines(db, search="WIDGET")
            self.assertEqual(ftotal, 1)
            self.assertEqual(found[0]["material_name"], "WIDGET-X")

            owners = pv.line_owners(db)
            self.assertEqual({o["emp_code"] for o in owners}, {"E1", "E2"})
            self.assertEqual([o["name"] for o in owners if o["emp_code"] == "E1"], ["Pramod"])


class LineCancelTests(unittest.TestCase):
    def test_line_cancel_touches_only_that_line(self):
        with _temp_db() as db:
            a = _line(db, crm="C1"); b = _line(db, crm="C2")  # same PO1
            res = pcs.request_line_cancellation(
                db, record_id=a.id, requested_by="admin@x.com", remark="wrong spec"
            )
            self.assertEqual(res["cancellation_status"], "PENDING")
            db.refresh(a); db.refresh(b)
            self.assertEqual(a.cancellation_status, "PENDING")
            self.assertEqual(a.cancel_remark, "wrong spec")
            self.assertIsNone(b.cancellation_status)

    def test_unknown_record_returns_none(self):
        with _temp_db() as db:
            self.assertIsNone(pcs.request_line_cancellation(db, record_id=999, requested_by="x"))


if __name__ == "__main__":
    unittest.main()
