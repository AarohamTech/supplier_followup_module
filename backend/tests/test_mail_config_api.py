"""Router-level tests for main mailbox config + per-user sending identities.

Calls the router functions directly with an explicit db (the admin RBAC guard is a
FastAPI dependency, verified elsewhere), focusing on masking, encryption-at-rest,
keep-existing-password, and identity CRUD/validation.
"""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, UserMailIdentity  # noqa: F401
from app.models.app_setting import AppSetting
from app.routers import mail_identities as mi
from app.routers import settings as st
from app.services import mail_config_service as mc


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


class MailConfigApiTests(unittest.TestCase):
    def test_put_smtp_masks_and_encrypts(self) -> None:
        with _temp_db() as db:
            payload = st.SmtpConfigPayload(
                enabled=True, host="smtp.corp", port=465, user="mailer",
                **{"from": "noreply@corp.test"}, password="topsecret",
            )
            out = st.put_smtp_config(payload, db)
            self.assertEqual(out["smtp"]["host"], "smtp.corp")
            self.assertEqual(out["smtp"]["port"], 465)
            self.assertTrue(out["smtp"]["password_set"])
            self.assertNotIn("topsecret", str(out))          # masked in response
            raw = db.get(AppSetting, mc.MAIL_CONFIG_KEY).value
            self.assertTrue(raw["smtp"]["password_enc"].startswith("enc:v1:"))
            self.assertNotIn("topsecret", str(raw))           # encrypted at rest

    def test_put_smtp_blank_password_keeps_existing(self) -> None:
        with _temp_db() as db:
            st.put_smtp_config(st.SmtpConfigPayload(
                enabled=True, host="h", user="u", **{"from": "f@c.test"}, password="keepme",
            ), db)
            # second save without a password
            st.put_smtp_config(st.SmtpConfigPayload(
                enabled=False, host="h2", user="u2", **{"from": "f2@c.test"},
            ), db)
            cfg = mc.get_smtp_config(db)
            self.assertEqual(cfg.password, "keepme")
            self.assertEqual(cfg.host, "h2")
            self.assertFalse(cfg.enabled)

    def test_get_mail_config_returns_both(self) -> None:
        with _temp_db() as db:
            out = st.get_mail_config(db)
            self.assertIn("smtp", out)
            self.assertIn("imap", out)

    def test_put_imap_roundtrip(self) -> None:
        with _temp_db() as db:
            out = st.put_imap_config(st.ImapConfigPayload(
                enabled=True, protocol="pop3", use_ssl=True, host="pop.corp",
                port=995, user="box", folder="INBOX", password="imappw",
            ), db)
            self.assertEqual(out["imap"]["protocol"], "POP3")     # normalized upper
            self.assertTrue(out["imap"]["use_ssl"])
            cfg = mc.get_imap_config(db)
            self.assertEqual(cfg.password, "imappw")


class MailIdentityApiTests(unittest.TestCase):
    def _staff(self, db, email="agent@corp.test") -> User:
        u = User(email=email, hashed_password="x", role="user")
        db.add(u); db.commit(); db.refresh(u)
        return u

    def test_upsert_and_list_identity(self) -> None:
        with _temp_db() as db:
            u = self._staff(db)
            row = mi.upsert_identity(u.id, mi.IdentityPayload(
                enabled=True, smtp_host="smtp.me", smtp_port=587, smtp_user="me",
                from_email="", use_ssl=False, password="mypw",
            ), db)
            # from_email defaults to the account email when omitted
            self.assertEqual(row["identity"]["from_email"], "agent@corp.test")
            self.assertTrue(row["identity"]["password_set"])
            self.assertNotIn("mypw", str(row))

            listing = mi.list_identities(db)
            me = [r for r in listing["users"] if r["user_id"] == u.id][0]
            self.assertEqual(me["identity"]["smtp_host"], "smtp.me")

            # stored encrypted
            ident = db.get(UserMailIdentity, 1)
            self.assertTrue(ident.smtp_password_enc.startswith("enc:v1:"))

    def test_delete_identity(self) -> None:
        with _temp_db() as db:
            u = self._staff(db)
            mi.upsert_identity(u.id, mi.IdentityPayload(smtp_host="h", password="p"), db)
            out = mi.delete_identity(u.id, db)
            self.assertTrue(out["ok"])
            with self.assertRaises(HTTPException):
                mi.delete_identity(u.id, db)  # already gone → 404

    def test_supplier_account_rejected(self) -> None:
        with _temp_db() as db:
            u = User(email="vend@x.com", hashed_password="x", role="supplier", supplier_id=7)
            db.add(u); db.commit(); db.refresh(u)
            with self.assertRaises(HTTPException) as ctx:
                mi.upsert_identity(u.id, mi.IdentityPayload(smtp_host="h", password="p"), db)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_list_excludes_suppliers(self) -> None:
        with _temp_db() as db:
            self._staff(db, email="staff@corp.test")
            db.add(User(email="sup@x.com", hashed_password="x", role="supplier", supplier_id=1))
            db.commit()
            listing = mi.list_identities(db)
            emails = {r["email"] for r in listing["users"]}
            self.assertIn("staff@corp.test", emails)
            self.assertNotIn("sup@x.com", emails)


if __name__ == "__main__":
    unittest.main()
