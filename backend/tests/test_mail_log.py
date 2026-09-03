"""Mail Log endpoint: every outgoing message with status, recipients, and the
send-window hold state; viewer+ may read it, supplier/employee accounts may not."""
import unittest
import unittest.mock
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.database import Base, get_db
from app.models import CommunicationMessage
from app.services import company_service, settings_service, user_service

# 12:00 IST = 06:30 UTC — inside office hours, so the default window is shut.
OFFICE_HOURS_UTC = datetime(2026, 9, 3, 6, 30)


class MailLogTests(unittest.TestCase):
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

    def _token(self, email, role):
        user_service.create_user(self.db, email=email, password="secret123", full_name=role, role=role)
        r = self.client.post("/api/auth/login", json={"email": email, "password": "secret123"})
        return r.json()["access_token"]

    def _seed(self):
        rows = [
            CommunicationMessage(direction="OUTGOING", status="SENT", mail_type="PO_FOLLOWUP_GREEN",
                                 supplier_name="ACME TOOLS", supplier_po_no="PO1", subject="Ack PO1",
                                 to_emails=["ops@acme.test"], sent_at=datetime(2026, 9, 3, 5, 0)),
            CommunicationMessage(direction="OUTGOING", status="READY", mail_type="PO_FOLLOWUP_RED",
                                 supplier_name="ACME TOOLS", supplier_po_no="PO2", subject="Urgent PO2",
                                 to_emails=["ops@acme.test"]),
            CommunicationMessage(direction="OUTGOING", status="READY", mail_type="SUPPLIER_PORTAL_CREDENTIALS",
                                 supplier_name="BOLT CO", subject="Your login", to_emails=["a@bolt.test"]),
            CommunicationMessage(direction="OUTGOING", status="FAILED", mail_type="HUB_COMPOSE",
                                 supplier_name="BOLT CO", subject="Compose", to_emails=["a@bolt.test"],
                                 error_message="535 auth failed"),
            CommunicationMessage(direction="INCOMING", status="RECEIVED", supplier_name="ACME TOOLS",
                                 subject="Re: Ack PO1", body="ok"),
        ]
        for r in rows:
            self.db.add(r)
        self.db.commit()

    def test_lists_outgoing_only_with_counts_and_hold_state(self):
        self._seed()
        token = self._token("viewer@x.com", "viewer")
        with unittest.mock.patch("app.routers.mail_log.datetime") as dt:
            dt.utcnow.return_value = OFFICE_HOURS_UTC
            dt.combine = datetime.combine
            dt.min = datetime.min
            r = self.client.get("/api/mail-log", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["counts"]["SENT"], 1)
        self.assertEqual(data["counts"]["READY"], 2)
        self.assertEqual(data["counts"]["FAILED"], 1)
        by_type = {i["mail_type"]: i for i in data["items"]}
        # RED follow-up waits for the window; credentials never do; GREEN went out.
        self.assertTrue(by_type["PO_FOLLOWUP_RED"]["held"])
        self.assertEqual(by_type["PO_FOLLOWUP_RED"]["held_until"], "19:00")
        self.assertFalse(by_type["SUPPLIER_PORTAL_CREDENTIALS"]["held"])
        self.assertFalse(by_type["PO_FOLLOWUP_GREEN"]["held"])
        self.assertEqual(by_type["HUB_COMPOSE"]["error_message"], "535 auth failed")
        self.assertEqual(by_type["PO_FOLLOWUP_GREEN"]["to_emails"], ["ops@acme.test"])
        self.assertFalse(data["window"]["open"])

    def test_filters_by_status_supplier_and_type(self):
        self._seed()
        token = self._token("user@x.com", "user")
        h = {"Authorization": f"Bearer {token}"}
        r = self.client.get("/api/mail-log?status=FAILED", headers=h).json()
        self.assertEqual([i["mail_type"] for i in r["items"]], ["HUB_COMPOSE"])
        r = self.client.get("/api/mail-log?search=bolt", headers=h).json()
        self.assertEqual(r["total"], 2)
        r = self.client.get("/api/mail-log?search=a@bolt.test", headers=h).json()
        self.assertEqual(r["total"], 2, "recipient address is searchable")
        r = self.client.get("/api/mail-log?mail_type=PO_FOLLOWUP_GREEN", headers=h).json()
        self.assertEqual(r["total"], 1)
        self.assertIn("PO_FOLLOWUP_GREEN", r["mail_types"])

    def test_export_is_an_xlsx(self):
        self._seed()
        token = self._token("mgr@x.com", "manager")
        r = self.client.get("/api/mail-log/export", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("spreadsheetml", r.headers["content-type"])
        self.assertTrue(r.content.startswith(b"PK"))

    def test_requires_login(self):
        r = self.client.get("/api/mail-log")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
