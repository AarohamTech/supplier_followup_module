"""Own-PO security boundary tests for the employee-scoped ASN + customer-mail
routers. In-memory SQLite; production data untouched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_eportal_scoped.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    Asn,
    CustomerMail,
    ProcurementRecord,
    SupplierMaster,
    User,
)
from app.routers import eportal_asns, eportal_mails  # noqa: E402
from app.services import asn_service, user_service  # noqa: E402


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


def _seed(db):
    sup = SupplierMaster(supplier_name="ACME TOOLS", is_active=True)
    db.add(sup)
    db.commit()
    db.refresh(sup)

    e1 = user_service.create_user(
        db, email="e1@employee.local", password="pw", full_name="Desk Owner One",
        role="employee", emp_code="E1", username="DESK1",
    )
    e2 = user_service.create_user(
        db, email="e2@employee.local", password="pw", full_name="Desk Owner Two",
        role="employee", emp_code="E2", username="DESK2",
    )
    db.add_all([
        ProcurementRecord(crm_no="C1", supplier_po_no="PO-1", material_name="Drill",
                          supplier_name="ACME TOOLS", owner_emp_code="E1"),
        ProcurementRecord(crm_no="C2", supplier_po_no="PO-2", material_name="Bit",
                          supplier_name="ACME TOOLS", owner_emp_code="E2"),
    ])
    db.commit()

    a1 = asn_service.create_asn(db, supplier_id=sup.id, supplier_name="ACME TOOLS",
                                supplier_po_no="PO-1", submit=True)
    a2 = asn_service.create_asn(db, supplier_id=sup.id, supplier_name="ACME TOOLS",
                                supplier_po_no="PO-2", submit=True)

    # Customer mails must come from the configured customer domain to appear.
    m1 = CustomerMail(from_email="buyer@zanvargroup.com", subject="About PO-1",
                      body="b", linked_supplier_po_no="PO-1", status="OPEN")
    m2 = CustomerMail(from_email="buyer@zanvargroup.com", subject="About PO-2",
                      body="b", linked_supplier_po_no="PO-2", status="OPEN")
    m3 = CustomerMail(from_email="ops@zanvargroup.com", subject="Allocated to one",
                      body="b", assigned_to="Desk Owner One", status="OPEN")
    m4 = CustomerMail(from_email="misc@zanvargroup.com", subject="Nobody's",
                      body="b", status="OPEN")
    db.add_all([m1, m2, m3, m4])
    db.commit()
    return sup, e1, e2, a1, a2, m1, m2, m3, m4


class EportalAsnScopeTests(unittest.TestCase):
    def test_list_and_detail_scoped_to_owned_pos(self):
        with _temp_db() as db:
            _, e1, e2, a1, a2, *_ = _seed(db)

            out = eportal_asns.list_asns(user=e1, db=db, tab=None, status=None, search=None)
            self.assertEqual(out.count, 1)
            self.assertEqual(out.items[0].supplier_po_no, "PO-1")

            got = eportal_asns.get_asn(a1.id, user=e1, db=db)
            self.assertEqual(got.id, a1.id)
            with self.assertRaises(HTTPException):
                eportal_asns.get_asn(a2.id, user=e1, db=db)

            s1 = eportal_asns.summary(user=e1, db=db)
            self.assertEqual(s1["total"], 1)
            s2 = eportal_asns.summary(user=e2, db=db)
            self.assertEqual(s2["total"], 1)

    def test_no_owned_pos_sees_nothing(self):
        with _temp_db() as db:
            _seed(db)
            lonely = user_service.create_user(
                db, email="e3@employee.local", password="pw", full_name="No Desk",
                role="employee", emp_code="E3", username="DESK3",
            )
            out = eportal_asns.list_asns(user=lonely, db=db, tab=None, status=None, search=None)
            self.assertEqual(out.count, 0)
            self.assertEqual(eportal_asns.summary(user=lonely, db=db)["total"], 0)


class EportalMailScopeTests(unittest.TestCase):
    def test_list_includes_linked_and_allocated_only(self):
        with _temp_db() as db:
            _, e1, _, _, _, m1, m2, m3, m4 = _seed(db)
            out = eportal_mails.list_mails(
                user=e1, db=db, status=None, search=None, limit=100, offset=0
            )
            ids = {m.id for m in out["items"]}
            self.assertIn(m1.id, ids)   # linked to owned PO-1
            self.assertIn(m3.id, ids)   # allocated by name
            self.assertNotIn(m2.id, ids)  # someone else's PO
            self.assertNotIn(m4.id, ids)  # unlinked + unassigned
            self.assertEqual(out["total"], 2)

    def test_detail_and_reply_guards_404_out_of_scope(self):
        with _temp_db() as db:
            _, e1, _, _, _, m1, m2, *_ = _seed(db)
            got = eportal_mails.get_mail(m1.id, user=e1, db=db)
            self.assertEqual(got.id, m1.id)
            with self.assertRaises(HTTPException):
                eportal_mails.get_mail(m2.id, user=e1, db=db)
            with self.assertRaises(HTTPException):
                eportal_mails.list_replies(m2.id, user=e1, db=db)


if __name__ == "__main__":
    unittest.main()
