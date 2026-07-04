"""Per-user "send as" identity resolution + main-mailbox fallback."""
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import secret_crypto
from app.database import Base
from app.models import CommunicationMessage, ProcurementRecord, User, UserMailIdentity
from app.services import communication_message_service as msg_service
from app.services import mail_identity_service
from app.services.mail_config_service import SmtpConfig
from app.workers import mail_send_worker


def _main_cfg() -> SmtpConfig:
    return SmtpConfig(enabled=True, host="smtp.main", port=587, user="", password="", from_addr="mainfrom")


class SendAsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool, future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def _user(self, db, email="agent@corp.test", emp_code=None) -> User:
        u = User(email=email, hashed_password="x", role="user", emp_code=emp_code)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def _identity(self, db, user_id, *, enabled=True, host="smtp.personal", frm="me@corp.test"):
        db.add(UserMailIdentity(
            user_id=user_id, enabled=enabled, smtp_host=host, smtp_port=587,
            smtp_user="me", smtp_password_enc=secret_crypto.encrypt("pw"), from_email=frm,
        ))
        db.commit()

    # ── resolution ────────────────────────────────────────────────────────────
    def test_resolves_personal_by_sender_email(self) -> None:
        db = self.Session()
        try:
            u = self._user(db)
            self._identity(db, u.id, frm="me@corp.test")
            msg = msg_service.queue_outgoing_message(
                db, to_emails=["v@x.com"], subject="s", body="b", sender_email=u.email, commit=True
            )
            cfg = mail_identity_service.resolve_personal_smtp(db, msg)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.host, "smtp.personal")
            self.assertEqual(cfg.from_addr, "me@corp.test")
            self.assertEqual(cfg.password, "pw")  # decrypted
        finally:
            db.close()

    def test_resolves_personal_by_po_owner_when_no_sender(self) -> None:
        db = self.Session()
        try:
            u = self._user(db, email="owner@corp.test", emp_code="E42")
            self._identity(db, u.id, frm="owner@corp.test")
            rec = ProcurementRecord(
                crm_no="CRM-1", material_name="Widget", supplier_po_no="PO-1", owner_emp_code="E42"
            )
            db.add(rec)
            db.commit()
            msg = msg_service.queue_outgoing_message(
                db, to_emails=["v@x.com"], subject="s", body="b",
                procurement_record_id=rec.id, commit=True,
            )
            cfg = mail_identity_service.resolve_personal_smtp(db, msg)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.from_addr, "owner@corp.test")
        finally:
            db.close()

    def test_disabled_identity_falls_back_to_none(self) -> None:
        db = self.Session()
        try:
            u = self._user(db)
            self._identity(db, u.id, enabled=False)
            msg = msg_service.queue_outgoing_message(
                db, to_emails=["v@x.com"], subject="s", body="b", sender_email=u.email, commit=True
            )
            self.assertIsNone(mail_identity_service.resolve_personal_smtp(db, msg))
        finally:
            db.close()

    def test_no_identity_returns_none(self) -> None:
        db = self.Session()
        try:
            u = self._user(db)
            msg = msg_service.queue_outgoing_message(
                db, to_emails=["v@x.com"], subject="s", body="b", sender_email=u.email, commit=True
            )
            self.assertIsNone(mail_identity_service.resolve_personal_smtp(db, msg))
        finally:
            db.close()

    # ── send path ─────────────────────────────────────────────────────────────
    def test_send_uses_personal_identity_from_address(self) -> None:
        db = self.Session()
        try:
            u = self._user(db)
            self._identity(db, u.id, host="smtp.personal", frm="me@corp.test")
            mid = msg_service.queue_outgoing_message(
                db, to_emails=["v@x.com"], subject="s", body="b", sender_email=u.email, commit=True
            ).id
        finally:
            db.close()

        opened = []
        sent = []

        def fake_open(cfg=None):
            opened.append(cfg)
            client = MagicMock()
            client.__enter__ = MagicMock(return_value=client)
            client.__exit__ = MagicMock(return_value=False)
            client.send_message = lambda em: sent.append(em)
            return client

        with patch.object(mail_send_worker, "SessionLocal", self.Session), \
             patch.object(mail_send_worker.mail_config_service, "get_smtp_config", return_value=_main_cfg()), \
             patch.object(mail_send_worker, "_open_client", side_effect=fake_open):
            result = mail_send_worker.send_ready_messages(limit=1)

        self.assertEqual(result["results"][0]["status"], "SENT")
        self.assertEqual(result["results"][0]["via"], "personal")
        # opened the personal server, and From is the user's address
        self.assertEqual(opened[0].host, "smtp.personal")
        self.assertEqual(sent[0]["From"], "me@corp.test")

    def test_personal_failure_falls_back_to_main_mailbox(self) -> None:
        db = self.Session()
        try:
            u = self._user(db)
            self._identity(db, u.id, host="smtp.personal", frm="me@corp.test")
            mid = msg_service.queue_outgoing_message(
                db, to_emails=["v@x.com"], subject="s", body="b", sender_email=u.email, commit=True
            ).id
        finally:
            db.close()

        sent_via = []

        def fake_open(cfg=None):
            client = MagicMock()
            client.__enter__ = MagicMock(return_value=client)
            client.__exit__ = MagicMock(return_value=False)
            if cfg is not None and cfg.host == "smtp.personal":
                client.send_message = MagicMock(side_effect=RuntimeError("personal down"))
            else:
                client.send_message = lambda em: sent_via.append((cfg.host, em["From"]))
            return client

        with patch.object(mail_send_worker, "SessionLocal", self.Session), \
             patch.object(mail_send_worker.mail_config_service, "get_smtp_config", return_value=_main_cfg()), \
             patch.object(mail_send_worker, "_open_client", side_effect=fake_open):
            result = mail_send_worker.send_ready_messages(limit=1)

        self.assertEqual(result["results"][0]["status"], "SENT")
        self.assertEqual(result["results"][0]["via"], "main_fallback")
        self.assertIn("personal down", result["results"][0]["personal_error"])
        # delivered via the main mailbox with the main From
        self.assertEqual(sent_via, [("smtp.main", "mainfrom")])
        db = self.Session()
        try:
            self.assertEqual(db.get(CommunicationMessage, mid).status, "SENT")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
