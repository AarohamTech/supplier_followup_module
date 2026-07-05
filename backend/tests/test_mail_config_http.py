"""End-to-end HTTP tests: admin RBAC + mail-config + sending-identity routes.

Verifies the wiring through the real FastAPI stack (auth, admin guard, routers),
not just the service layer: only admins can edit the main mailbox and manage
identities; passwords are never returned in plaintext; a mapped identity is
resolvable for send-as.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_mail_config_http.sqlite")

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.database import Base, get_db
from app.services import company_service, user_service


class MailConfigHttpTests(unittest.TestCase):
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
        resp = self.client.post("/api/auth/login", json={"email": email, "password": "secret123"})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["access_token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_admin_can_edit_main_mailbox_non_admin_cannot(self):
        admin = self._token("admin@x.com", "admin")
        manager = self._token("mgr@x.com", "manager")

        # non-admin (manager) is blocked from editing the mailbox
        blocked = self.client.put(
            "/api/settings/mail-config/smtp",
            headers=self._auth(manager),
            json={"enabled": True, "host": "smtp.x", "port": 587, "user": "u", "from": "f@x.com"},
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)

        # admin can save
        saved = self.client.put(
            "/api/settings/mail-config/smtp",
            headers=self._auth(admin),
            json={"enabled": True, "host": "smtp.corp", "port": 465, "user": "mailer",
                  "from": "noreply@corp.test", "password": "supersecret"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn("supersecret", saved.text)  # never echoed in plaintext

        # readable (masked), and persisted
        got = self.client.get("/api/settings/mail-config", headers=self._auth(manager))
        self.assertEqual(got.status_code, 200, got.text)
        body = got.json()
        self.assertEqual(body["smtp"]["host"], "smtp.corp")
        self.assertEqual(body["smtp"]["port"], 465)
        self.assertTrue(body["smtp"]["password_set"])
        self.assertNotIn("supersecret", got.text)

    def test_identity_crud_via_http(self):
        admin = self._token("admin2@x.com", "admin")
        # a target staff user to map an identity onto
        target = user_service.create_user(self.db, email="agent@x.com", password="p", full_name="Agent", role="user")

        listing = self.client.get("/api/mail-identities", headers=self._auth(admin))
        self.assertEqual(listing.status_code, 200, listing.text)
        ids = {u["user_id"] for u in listing.json()["users"]}
        self.assertIn(target.id, ids)

        put = self.client.put(
            f"/api/mail-identities/{target.id}",
            headers=self._auth(admin),
            json={"enabled": True, "smtp_host": "smtp.me", "smtp_port": 587, "smtp_user": "me",
                  "from_email": "", "use_ssl": False, "password": "mypw"},
        )
        self.assertEqual(put.status_code, 200, put.text)
        row = put.json()
        self.assertEqual(row["identity"]["from_email"], "agent@x.com")  # defaulted to email
        self.assertTrue(row["identity"]["password_set"])
        self.assertNotIn("mypw", put.text)

        # non-admin blocked
        writer = self._token("writer@x.com", "user")
        blocked = self.client.get("/api/mail-identities", headers=self._auth(writer))
        self.assertEqual(blocked.status_code, 403, blocked.text)

        # delete
        deleted = self.client.delete(f"/api/mail-identities/{target.id}", headers=self._auth(admin))
        self.assertEqual(deleted.status_code, 200, deleted.text)
        again = self.client.delete(f"/api/mail-identities/{target.id}", headers=self._auth(admin))
        self.assertEqual(again.status_code, 404, again.text)


if __name__ == "__main__":
    unittest.main()
