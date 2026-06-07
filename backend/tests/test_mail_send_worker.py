import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.workers import mail_send_worker


class MailSendWorkerTests(unittest.TestCase):
    def test_config_ready_requires_complete_auth_pair(self) -> None:
        with patch.multiple(
            mail_send_worker.settings,
            SMTP_ENABLED=True,
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="noreply@example.com",
            SMTP_USER="mailer",
            SMTP_PASSWORD="",
        ):
            ready, reason = mail_send_worker._config_ready()

        self.assertFalse(ready)
        self.assertEqual(reason, "SMTP_USER and SMTP_PASSWORD must both be set")

    @patch("app.workers.mail_send_worker.smtplib.SMTP")
    def test_smtp_connection_uses_starttls_and_login(self, smtp_cls: MagicMock) -> None:
        client = MagicMock()
        smtp_cls.return_value = client

        with patch.multiple(
            mail_send_worker.settings,
            SMTP_ENABLED=True,
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_FROM="noreply@example.com",
            SMTP_USER="mailer",
            SMTP_PASSWORD="secret",
        ):
            result = mail_send_worker.test_smtp_connection()

        self.assertTrue(result["ok"])
        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        client.ehlo.assert_called()
        client.starttls.assert_called_once_with()
        client.login.assert_called_once_with("mailer", "secret")

    @patch("app.workers.mail_send_worker.msg_service.mark_status")
    def test_sync_delivery_updates_history_and_procurement(self, mark_status: MagicMock) -> None:
        msg = SimpleNamespace(
            id=5,
            procurement_record_id=11,
            raw_payload={"mail_history_id": 19},
            sent_at=None,
        )
        history = SimpleNamespace(
            sent_status="READY",
            sent_at=None,
            remarks="old error",
            material_name="Steel",
            mail_type="YELLOW_REMINDER",
            supplier_po_no="PO-42",
            supplier_name="Acme",
        )
        rec = SimpleNamespace(mail_status="READY", last_followup_date=None, followup_count=0)
        db = MagicMock()
        db.get.side_effect = lambda model, key: history if key == 19 else rec

        mail_send_worker._sync_delivery_state(db, msg, status="SENT")

        mark_status.assert_called_once_with(db, 5, "SENT", error=None, commit=False)
        self.assertEqual(history.sent_status, "SENT")
        self.assertIsNotNone(history.sent_at)
        self.assertIsNone(history.remarks)
        self.assertEqual(rec.mail_status, "SENT")
        self.assertIsNotNone(rec.last_followup_date)
        self.assertEqual(rec.followup_count, 1)


if __name__ == "__main__":
    unittest.main()