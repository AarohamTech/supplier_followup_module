"""#1 employee portal PO grouping is supplier-scoped; #2 delete-PO API.

CRM PoNo is recycled across suppliers, so one employee can own the same PO number
for two different suppliers — they must appear as two distinct POs, and materials
must not mix. Delete-PO removes one supplier's lines only.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_portal_scope.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import ProcurementRecord, User  # noqa: E402,F401
from app.routers import employee_portal, procurement  # noqa: E402
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


def _rec(crm, sup, mat, po="000440", emp="E1", signal="BLACK"):
    return ProcurementRecord(
        crm_no=crm, supplier_po_no=po, material_name=mat, supplier_name=sup,
        owner_emp_code=emp, signal=signal, po_status="APPROVED",
    )


class EmployeePortalScopeTests(unittest.TestCase):
    def _emp(self, db):
        return user_service.create_user(
            db, email="e1@employee.local", password="pw", full_name="Owner",
            role="employee", emp_code="E1", username="DESK1",
        )

    def test_shared_po_number_lists_as_two_distinct_pos(self):
        with _temp_db() as db:
            emp = self._emp(db)
            db.add_all([
                _rec("2627-1", "Vedant Tools Pvt Ltd", "SC DRILL"),
                _rec("2627-1", "GLOBAL TOOLS PRIVATE LIMITED", "SPOT FACE LH"),
                _rec("2627-1", "GLOBAL TOOLS PRIVATE LIMITED", "SPOT FACE RH"),
            ])
            db.commit()

            resp = employee_portal.list_pos(user=emp, db=db)
            self.assertEqual(resp.count, 2)  # two suppliers, not one merged PO
            by_sup = {i.supplier_name: i.material_count for i in resp.items}
            self.assertEqual(by_sup["Vedant Tools Pvt Ltd"], 1)
            self.assertEqual(by_sup["GLOBAL TOOLS PRIVATE LIMITED"], 2)

    def test_materials_are_supplier_scoped(self):
        with _temp_db() as db:
            emp = self._emp(db)
            db.add_all([
                _rec("2627-1", "Vedant Tools Pvt Ltd", "SC DRILL"),
                _rec("2627-1", "GLOBAL TOOLS PRIVATE LIMITED", "SPOT FACE LH"),
            ])
            db.commit()

            mats = employee_portal.po_materials(
                "000440", supplier_name="Vedant Tools Pvt Ltd", user=emp, db=db
            )
            self.assertEqual([m.material_name for m in mats], ["SC DRILL"])


class DeletePoTests(unittest.TestCase):
    def test_delete_po_removes_only_that_supplier(self):
        with _temp_db() as db:
            db.add_all([
                _rec("2627-1", "Vedant Tools Pvt Ltd", "SC DRILL"),
                _rec("2627-1", "GLOBAL TOOLS PRIVATE LIMITED", "SPOT FACE LH"),
            ])
            db.commit()

            out = procurement.delete_po(
                supplier_po_no="000440", supplier_name="vedant tools pvt ltd", db=db
            )
            self.assertEqual(out["deleted_lines"], 1)
            remaining = db.scalars(select(ProcurementRecord)).all()
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].supplier_name, "GLOBAL TOOLS PRIVATE LIMITED")

    def test_delete_po_404_when_no_match(self):
        with _temp_db() as db:
            db.add(_rec("2627-1", "Vedant Tools Pvt Ltd", "SC DRILL"))
            db.commit()
            with self.assertRaises(HTTPException):
                procurement.delete_po(supplier_po_no="999999", supplier_name="Nobody", db=db)


if __name__ == "__main__":
    unittest.main()
