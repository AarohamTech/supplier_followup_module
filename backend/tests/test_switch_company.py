import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_switch_company.sqlite")

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.main as main_mod
from app.core.security import decode_token
from app.services import company_service, user_service


class SwitchCompanyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.Session()
        company_service.seed_companies(self.db)
        user_service.create_user(
            self.db,
            email="manager@example.com",
            password="secret123",
            full_name="Manager",
            role="manager",
            is_active=True,
        )
        main_mod.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(main_mod.app)

        login_resp = self.client.post(
            "/api/auth/login",
            json={"email": "manager@example.com", "password": "secret123"},
        )
        self.assertEqual(login_resp.status_code, 200, login_resp.text)
        self.token = login_resp.json()["access_token"]

    def tearDown(self):
        main_mod.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_switch_reissues_token(self):
        resp = self.client.post(
            "/api/auth/switch-company",
            json={"company": "101"},
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["company"]["code"], "101")
        decoded = decode_token(body["access_token"])
        self.assertEqual(decoded["company"], "101")

    def test_switch_rejects_unknown(self):
        resp = self.client.post(
            "/api/auth/switch-company",
            json={"company": "999"},
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 400, resp.text)


if __name__ == "__main__":
    unittest.main()
