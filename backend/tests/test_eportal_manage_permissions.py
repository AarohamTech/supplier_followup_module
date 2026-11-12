"""Employee-portal Supplier Assignment + Email Master, gated per employee.

- both permission flags are granted by default (NULL in old rows = granted)
- an admin switches them off per employee on Employee Logins (PATCH)
- the flag is enforced server-side on every /api/eportal/manage route
- staff routes keep their behaviour and still reject employee accounts
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_eportal_manage.sqlite")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.main as main_mod  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models import SupplierAssignment, SupplierEmail, SupplierMaster, User  # noqa: E402,F401
from app.models.supplier_email_audit import SupplierEmailAudit  # noqa: E402
from app.schemas.user import UserOut  # noqa: E402
from app.services import company_service, employee_permissions, supplier_account_service, user_service  # noqa: E402


class EportalManageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)()
        company_service.seed_companies(self.db)
        main_mod.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(main_mod.app)
        self.mail_patch = patch.object(supplier_account_service, "send_credentials_email", return_value=False)
        self.mail_patch.start()

        self.emp = user_service.create_user(
            self.db, email="desk1@employee.local", password="secret123", full_name="Desk One",
            role="employee", emp_code="E1", username="DESK1",
        )
        self.admin_h = self._login({"email": "admin@x.com"}, create=("admin@x.com", "admin"))
        self.emp_h = self._login({"username": "DESK1"})
        self.supplier = SupplierMaster(supplier_name="SHIVAM ENGINEERS")
        self.db.add(self.supplier)
        self.db.commit()

    def tearDown(self):
        self.mail_patch.stop()
        main_mod.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _login(self, ident, create=None):
        if create:
            user_service.create_user(self.db, email=create[0], password="secret123", role=create[1])
        r = self.client.post("/api/auth/login", json={**ident, "password": "secret123"})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ── defaults ──
    def test_flags_default_to_granted_and_null_means_granted(self):
        self.assertTrue(employee_permissions.has_permission(self.emp, employee_permissions.EMAIL_MASTER))
        self.emp.can_manage_email_master = None  # a row that predates the column
        self.emp.can_manage_supplier_assignments = None
        self.db.commit()
        self.assertTrue(employee_permissions.has_permission(self.emp, employee_permissions.EMAIL_MASTER))
        out = UserOut.model_validate(self.emp)
        self.assertTrue(out.can_manage_email_master)
        self.assertTrue(out.can_manage_supplier_assignments)
        me = self.client.get("/api/auth/me", headers=self.emp_h).json()
        self.assertTrue(me["can_manage_email_master"])
        self.assertTrue(me["can_manage_supplier_assignments"])
        # Staff and supplier accounts never hold employee permissions.
        staff = user_service.get_by_email(self.db, "admin@x.com")
        self.assertFalse(employee_permissions.has_permission(staff, employee_permissions.EMAIL_MASTER))

    # ── Supplier Assignment ──
    def test_employee_can_list_and_set_assignees(self):
        target = user_service.create_user(self.db, email="agent@x.com", password="p" * 8, role="user")
        r = self.client.get("/api/eportal/manage/supplier-assignments", headers=self.emp_h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(any(s["supplier_id"] == self.supplier.id for s in r.json()["suppliers"]))
        au = self.client.get("/api/eportal/manage/supplier-assignments/assignable-users", headers=self.emp_h)
        self.assertEqual(au.status_code, 200, au.text)
        put = self.client.put(
            f"/api/eportal/manage/supplier-assignments/{self.supplier.id}",
            headers=self.emp_h, json={"user_ids": [target.id, self.emp.id]},
        )
        self.assertEqual(put.status_code, 200, put.text)
        self.assertEqual({a["user_id"] for a in put.json()["assignees"]}, {target.id, self.emp.id})

    def test_assignments_blocked_when_admin_switches_flag_off(self):
        r = self.client.patch(
            f"/api/employee-accounts/{self.emp.id}", headers=self.admin_h,
            json={"can_manage_supplier_assignments": False},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["can_manage_supplier_assignments"])
        self.assertTrue(r.json()["can_manage_email_master"])  # untouched
        for method, url, body in (
            ("get", "/api/eportal/manage/supplier-assignments", None),
            ("get", "/api/eportal/manage/supplier-assignments/assignable-users", None),
            ("put", f"/api/eportal/manage/supplier-assignments/{self.supplier.id}", {"user_ids": []}),
        ):
            resp = getattr(self.client, method)(url, headers=self.emp_h, **({"json": body} if body else {}))
            self.assertEqual(resp.status_code, 403, f"{method} {url}: {resp.text}")
        # Email Master is still allowed.
        self.assertEqual(
            self.client.get("/api/eportal/manage/supplier-emails", headers=self.emp_h).status_code, 200)
        # Switch it back on.
        self.client.patch(f"/api/employee-accounts/{self.emp.id}", headers=self.admin_h,
                          json={"can_manage_supplier_assignments": True})
        self.assertEqual(
            self.client.get("/api/eportal/manage/supplier-assignments", headers=self.emp_h).status_code, 200)

    # ── Email Master ──
    def test_employee_can_add_and_edit_mapping(self):
        sup = self.client.get("/api/eportal/manage/suppliers", headers=self.emp_h)
        self.assertEqual(sup.status_code, 200, sup.text)
        self.assertEqual(sup.json()[0]["supplier_name"], "SHIVAM ENGINEERS")
        created = self.client.post("/api/eportal/manage/supplier-emails", headers=self.emp_h, json={
            "supplier_id": self.supplier.id, "to_emails": ["shivam.engineers@rediffmail.com"]})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual([c["email"] for c in created.json()["provisioning"]["created"]],
                         ["shivam.engineers@rediffmail.com"])
        eid = created.json()["id"]
        upd = self.client.put(f"/api/eportal/manage/supplier-emails/{eid}", headers=self.emp_h, json={
            "supplier_id": self.supplier.id, "to_emails": ["shivam.engineers@rediffmail.com"],
            "cc_emails": ["followuphconnect2012@gmail.com"]})
        self.assertEqual(upd.status_code, 200, upd.text)
        listed = self.client.get("/api/eportal/manage/supplier-emails", headers=self.emp_h).json()
        self.assertEqual(listed[0]["cc_emails"], ["followuphconnect2012@gmail.com"])
        # The change log records the employee as the actor.
        audit = self.db.query(SupplierEmailAudit).filter_by(action="UPDATE").one()
        self.assertEqual(audit.changed_by_id, self.emp.id)

    def test_email_master_blocked_when_flag_off(self):
        self.emp.can_manage_email_master = False
        self.db.commit()
        self.assertEqual(
            self.client.get("/api/eportal/manage/supplier-emails", headers=self.emp_h).status_code, 403)
        self.assertEqual(
            self.client.get("/api/eportal/manage/suppliers", headers=self.emp_h).status_code, 403)
        self.assertEqual(self.client.post("/api/eportal/manage/supplier-emails", headers=self.emp_h, json={
            "supplier_id": self.supplier.id, "to_emails": ["a@b.com"]}).status_code, 403)

    def test_staff_routes_unchanged_and_closed_to_employees(self):
        self.assertEqual(self.client.get("/api/supplier-emails", headers=self.emp_h).status_code, 403)
        self.assertEqual(self.client.get("/api/supplier-assignments", headers=self.emp_h).status_code, 403)
        self.assertEqual(self.client.get("/api/supplier-emails", headers=self.admin_h).status_code, 200)
        # Staff accounts cannot use the employee routes.
        self.assertEqual(
            self.client.get("/api/eportal/manage/supplier-emails", headers=self.admin_h).status_code, 403)

    def test_patch_rejects_non_admin(self):
        r = self.client.patch(f"/api/employee-accounts/{self.emp.id}", headers=self.emp_h,
                              json={"can_manage_email_master": False})
        self.assertEqual(r.status_code, 403)


class SchemaEvolveTests(unittest.TestCase):
    def test_existing_users_table_gets_flags_that_read_as_granted(self):
        from sqlalchemy import inspect, text
        from app.core.schema_evolve import ensure_columns, relax_users_email_unique

        engine = create_engine("sqlite://", future=True)
        with engine.begin() as conn:
            # A users table from before the permission columns existed.
            conn.execute(text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, "
                "hashed_password VARCHAR(255) NOT NULL, role VARCHAR(16) NOT NULL, "
                "is_active BOOLEAN NOT NULL, emp_code VARCHAR(32), supplier_id INTEGER)"
            ))
            conn.execute(text(
                "INSERT INTO users (email, hashed_password, role, is_active, emp_code) "
                "VALUES ('e@employee.local', 'x', 'employee', 1, 'E9')"
            ))
        ensure_columns(engine, [User.__table__])
        cols = {c["name"] for c in inspect(engine).get_columns("users")}
        self.assertIn("can_manage_supplier_assignments", cols)
        self.assertIn("can_manage_email_master", cols)
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT can_manage_supplier_assignments, can_manage_email_master FROM users")).one()
        # Backfilled with the default (or NULL) -- both mean granted.
        self.assertTrue(all(v is None or bool(v) for v in row))
        # Postgres-only index swap is a no-op elsewhere.
        self.assertEqual(relax_users_email_unique(engine), [])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
