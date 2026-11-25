"""Non-admin staff see only their own POs + assigned suppliers (client 2026-11-25).
In-memory SQLite; production data untouched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_staff_scope.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import ProcurementRecord, User  # noqa: E402,F401
from app.models.supplier import SupplierMaster  # noqa: E402
from app.models.supplier_assignment import SupplierAssignment  # noqa: E402
from app.models.supplier_email import SupplierEmail  # noqa: E402
from app.routers import procurement, supplier_emails, suppliers  # noqa: E402
from app.services import staff_scope, user_service  # noqa: E402


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


def _user(db, name, role, emp_code=None):
    return user_service.create_user(
        db, email=f"{name}@corp.com", password="x" * 8, role=role,
        emp_code=emp_code, username=name, full_name=name.title(),
    )


def _rec(db, po, name, owner=None, signal="RED"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}-{name}", material_name="Bolt", supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _supplier(db, name):
    s = SupplierMaster(supplier_name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class _Base(unittest.TestCase):
    def setUp(self):
        self._cm = _temp_db()
        self.db = self._cm.__enter__()
        db = self.db
        self.admin = _user(db, "admin", Role.ADMIN)
        self.vijay = _user(db, "vijay", Role.USER, emp_code="E2")
        self.mgr = _user(db, "mgr", Role.MANAGER, emp_code="E9")
        self.acme = _supplier(db, "ACME")
        self.beta = _supplier(db, "BETA")
        self.gamma = _supplier(db, "GAMMA")
        self.r1 = _rec(db, "001", "ACME", owner="E2")
        # Same recycled counter, other supplier, other owner: must NOT leak.
        self.r2 = _rec(db, "001", "BETA", owner="E7")
        self.r3 = _rec(db, "002", "GAMMA", owner="E7", signal="BLACK")
        db.add(SupplierAssignment(supplier_id=self.gamma.id, user_id=self.vijay.id))
        db.commit()

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def scope(self, user):
        return staff_scope.for_user(self.db, user)


class ScopeTests(_Base):
    def test_admin_unscoped(self):
        self.assertIsNone(self.scope(self.admin))

    def test_user_scope_owned_plus_assigned(self):
        s = self.scope(self.vijay)
        self.assertEqual(s.pairs, {("ACME", "001"), ("GAMMA", "002")})
        self.assertEqual(s.supplier_names, {"ACME", "GAMMA"})
        self.assertTrue(s.allows_pair("acme", "001"))
        self.assertFalse(s.allows_pair("BETA", "001"))
        self.assertTrue(s.allows_record(self.r3))
        self.assertFalse(s.allows_record(self.r2))

    def test_manager_is_scoped_and_sees_nothing_without_pos(self):
        s = self.scope(self.mgr)
        self.assertIsNotNone(s)
        rows = procurement.list_records(db=self.db, page=1, size=50, scope=s)
        self.assertEqual(rows.total, 0)


class ProcurementEndpointTests(_Base):
    def test_list_dashboard_breakdown_and_get_one(self):
        s = self.scope(self.vijay)
        rows = procurement.list_records(db=self.db, page=1, size=50, scope=s)
        self.assertEqual({(r.supplier_name, r.supplier_po_no) for r in rows.items},
                         {("ACME", "001"), ("GAMMA", "002")})
        # owner_emp_code from the client cannot widen the scope.
        rows = procurement.list_records(db=self.db, owner_emp_code="E7", page=1, size=50, scope=s)
        self.assertEqual(rows.total, 1)  # only the assigned GAMMA line

        k = procurement.dashboard(db=self.db, scope=s)
        self.assertEqual(k.total_records, 2)
        self.assertEqual(k.black_count, 1)
        self.assertEqual(procurement.dashboard(db=self.db, scope=None).total_records, 3)

        self.assertEqual(procurement.get_one(self.r1.id, db=self.db, scope=s).id, self.r1.id)
        with self.assertRaises(HTTPException) as ctx:
            procurement.get_one(self.r2.id, db=self.db, scope=s)
        self.assertEqual(ctx.exception.status_code, 404)


class SupplierEndpointTests(_Base):
    def test_suppliers_and_mappings_scoped(self):
        s = self.scope(self.vijay)
        names = {x["supplier_name"] for x in suppliers.list_suppliers(db=self.db, scope=s)}
        self.assertEqual(names, {"ACME", "GAMMA"})
        self.assertEqual(len(suppliers.list_suppliers(db=self.db, scope=None)), 3)
        with self.assertRaises(HTTPException):
            suppliers.get_supplier(self.beta.id, db=self.db, scope=s)

        for sup in (self.acme, self.beta):
            self.db.add(SupplierEmail(supplier_id=sup.id, supplier_name=sup.supplier_name,
                                      to_emails=[f"x@{sup.supplier_name.lower()}.com"]))
        self.db.commit()
        mapped = {m.supplier_name for m in supplier_emails.list_emails(db=self.db, scope=s)}
        self.assertEqual(mapped, {"ACME"})


if __name__ == "__main__":
    unittest.main()
