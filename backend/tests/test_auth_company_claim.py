import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_auth_company_claim.sqlite")

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.main as main_mod
from app.core.security import create_access_token, decode_token
from app.services import company_service, user_service


class AuthCompanyClaimTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.Session()
        company_service.seed_companies(self.db)
        main_mod.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(main_mod.app)

    def tearDown(self):
        main_mod.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_staff_login_embeds_requested_company(self):
        user_service.create_user(
            self.db,
            email="admin@example.com",
            password="secret123",
            full_name="Admin",
            role="admin",
            is_active=True,
        )
        resp = self.client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "secret123", "company": "101"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["company"]["code"], "101")
        decoded = decode_token(body["access_token"])
        self.assertEqual(decoded["company"], "101")

    def test_defaults_to_102_when_company_omitted(self):
        user_service.create_user(
            self.db,
            email="admin2@example.com",
            password="secret123",
            full_name="Admin2",
            role="admin",
            is_active=True,
        )
        resp = self.client.post(
            "/api/auth/login",
            json={"email": "admin2@example.com", "password": "secret123"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["company"]["code"], "102")

    def test_open_companies_list(self):
        resp = self.client.get("/api/auth/companies")
        self.assertEqual(resp.status_code, 200, resp.text)
        codes = {c["code"] for c in resp.json()}
        self.assertTrue({"101", "102"}.issubset(codes))

    # ── /switch-company ──────────────────────────────────────────────────────
    def _switch(self, user, code: str):
        token = create_access_token(subject=user.id, role=user.role, email=user.email,
                                    extra={"company": "102"})
        return self.client.post(
            "/api/auth/switch-company",
            json={"company": code},
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_plain_staff_user_can_switch_company(self):
        user = user_service.create_user(
            self.db, email="staff@example.com", password="secret123",
            full_name="Staff", role="user", is_active=True,
        )
        resp = self._switch(user, "101")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["company"]["code"], "101")
        self.assertEqual(decode_token(body["access_token"])["company"], "101")

    def test_employee_account_can_switch_company(self):
        user = user_service.create_user(
            self.db, email="emp@example.com", password="secret123",
            full_name="Employee", role="employee", is_active=True,
            emp_code="E42", username="EMP42",
            company_id=company_service.get_by_code(self.db, "102").id,
        )
        resp = self._switch(user, "101")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["company"]["code"], "101")
        self.assertEqual(decode_token(body["access_token"])["company"], "101")

    def test_supplier_account_cannot_switch_company(self):
        user = user_service.create_user(
            self.db, email="vendor@example.com", password="secret123",
            full_name="Vendor", role="supplier", is_active=True, supplier_id=7,
        )
        resp = self._switch(user, "101")
        self.assertEqual(resp.status_code, 403, resp.text)


if __name__ == "__main__":
    unittest.main()
