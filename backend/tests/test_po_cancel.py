"""Employee PO cancellation request: service scoping + eportal endpoint + list flag."""
import unittest
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ProcurementRecord, User
from app.routers import employee_portal as ep
from app.services import po_cancel_service as pcs


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


def _po(db, *, crm, po="PO9", supplier="Acme", owner="E1"):
    r = ProcurementRecord(crm_no=crm, material_name=f"M-{crm}", supplier_po_no=po, supplier_name=supplier, owner_emp_code=owner)
    db.add(r); db.commit()
    return r


class ServiceTests(unittest.TestCase):
    def test_request_is_scoped_to_owner_and_confirm_flips(self):
        with _temp_db() as db:
            _po(db, crm="C1", owner="E1"); _po(db, crm="C2", owner="E1"); _po(db, crm="C3", owner="E2")
            res = pcs.request_cancellation(db, supplier_po_no="PO9", supplier_name="Acme", requested_by="E1", owner_emp_code="E1")
            self.assertEqual(res["records_updated"], 2)
            self.assertEqual(res["cancellation_status"], "PENDING")
            statuses = {r.crm_no: r.cancellation_status for r in db.query(ProcurementRecord).all()}
            self.assertEqual(statuses, {"C1": "PENDING", "C2": "PENDING", "C3": None})

            # confirm flips only the pending ones
            self.assertEqual(pcs.confirm_cancellation(db, supplier_po_no="PO9", supplier_name="Acme"), 2)
            statuses = {r.crm_no: r.cancellation_status for r in db.query(ProcurementRecord).all()}
            self.assertEqual(statuses, {"C1": "CANCELLED", "C2": "CANCELLED", "C3": None})

    def test_request_unknown_or_unowned_returns_none(self):
        with _temp_db() as db:
            _po(db, crm="C1", owner="E1")
            self.assertIsNone(pcs.request_cancellation(db, supplier_po_no="PO9", supplier_name="Acme", requested_by="E9", owner_emp_code="E9"))
            self.assertIsNone(pcs.request_cancellation(db, supplier_po_no="NOPE", supplier_name="Acme", requested_by="E1", owner_emp_code="E1"))


class EndpointTests(unittest.TestCase):
    def test_endpoint_sets_pending_and_list_reflects_it(self):
        with _temp_db() as db:
            _po(db, crm="C1", owner="E1"); _po(db, crm="C2", owner="E1")
            emp = User(email="e1@x.com", hashed_password="x", role="employee", emp_code="E1")

            out = ep.request_po_cancel("PO9", supplier_name="Acme", user=emp, db=db)
            self.assertEqual(out["cancellation_status"], "PENDING")
            self.assertEqual(out["records_updated"], 2)

            # the employee PO list now shows the PO as pending-cancellation
            listing = ep.list_pos(user=emp, db=db)
            item = [p for p in listing.items if p.supplier_po_no == "PO9"][0]
            self.assertEqual(item.cancellation_status, "PENDING")

    def test_endpoint_404_for_unowned_po(self):
        with _temp_db() as db:
            _po(db, crm="C1", owner="E2")  # owned by someone else
            emp = User(email="e1@x.com", hashed_password="x", role="employee", emp_code="E1")
            with self.assertRaises(HTTPException) as ctx:
                ep.request_po_cancel("PO9", supplier_name="Acme", user=emp, db=db)
            self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
