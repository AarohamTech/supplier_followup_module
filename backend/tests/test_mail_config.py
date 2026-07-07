"""Editable main mailbox credentials: encryption, masking, and admin RBAC."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_mail_config.sqlite")

import unittest
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.core import secret_crypto
from app.database import Base, get_db
from app.models.app_setting import AppSetting
from app.routers import settings as st
from app.services import company_service, mail_config_service as mc, user_service


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


class ServiceTests(unittest.TestCase):
    def test_crypto_roundtrip_and_passthrough(self):
        tok = secret_crypto.encrypt("Tech#321")
        self.assertTrue(tok.startswith("enc:v1:"))
        self.assertEqual(secret_crypto.decrypt(tok), "Tech#321")
        self.assertEqual(secret_crypto.decrypt("legacyplain"), "legacyplain")
        self.assertEqual(secret_crypto.decrypt(""), "")

    def test_put_smtp_encrypts_at_rest_and_masks(self):
        with _temp_db() as db:
            out = st.put_smtp_config(
                st.SmtpConfigPayload(enabled=True, host="smtp.corp", port=465, user="mailer",
                                     **{"from": "noreply@corp.test"}, password="topsecret"),
                db,
            )
            self.assertEqual(out["smtp"]["host"], "smtp.corp")
            self.assertTrue(out["smtp"]["password_set"])
            self.assertNotIn("topsecret", str(out))
            raw = db.get(AppSetting, mc.MAIL_CONFIG_KEY).value
            self.assertTrue(raw["smtp"]["password_enc"].startswith("enc:v1:"))
            self.assertNotIn("topsecret", str(raw))
            # effective config decrypts back
            self.assertEqual(mc.get_smtp_config(db).password, "topsecret")

    def test_blank_password_keeps_existing(self):
        with _temp_db() as db:
            st.put_smtp_config(st.SmtpConfigPayload(enabled=True, host="h", user="u",
                                                    **{"from": "f@c.test"}, password="keepme"), db)
            st.put_smtp_config(st.SmtpConfigPayload(enabled=False, host="h2", user="u2",
                                                    **{"from": "f2@c.test"}), db)
            cfg = mc.get_smtp_config(db)
            self.assertEqual(cfg.password, "keepme")
            self.assertEqual(cfg.host, "h2")
            self.assertFalse(cfg.enabled)

    def test_put_imap_normalizes_protocol(self):
        with _temp_db() as db:
            out = st.put_imap_config(st.ImapConfigPayload(enabled=True, protocol="pop3", use_ssl=True,
                                                          host="pop.corp", port=995, user="box",
                                                          folder="INBOX", password="imappw"), db)
            self.assertEqual(out["imap"]["protocol"], "POP3")
            self.assertEqual(mc.get_imap_config(db).password, "imappw")


class HttpRbacTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool, future=True)
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
        return self.client.post("/api/auth/login", json={"email": email, "password": "secret123"}).json()["access_token"]

    def test_admin_only_edit_and_masked(self):
        admin = self._token("admin@x.com", "admin")
        manager = self._token("mgr@x.com", "manager")

        blocked = self.client.put("/api/settings/mail-config/smtp", headers={"Authorization": f"Bearer {manager}"},
                                  json={"enabled": True, "host": "smtp.x", "port": 587, "user": "u", "from": "f@x.com"})
        self.assertEqual(blocked.status_code, 403, blocked.text)

        saved = self.client.put("/api/settings/mail-config/smtp", headers={"Authorization": f"Bearer {admin}"},
                                json={"enabled": True, "host": "smtp.corp", "port": 465, "user": "mailer",
                                      "from": "noreply@corp.test", "password": "supersecret"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn("supersecret", saved.text)

        got = self.client.get("/api/settings/mail-config", headers={"Authorization": f"Bearer {manager}"})
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.json()["smtp"]["host"], "smtp.corp")
        self.assertTrue(got.json()["smtp"]["password_set"])
        self.assertNotIn("supersecret", got.text)


if __name__ == "__main__":
    unittest.main()
