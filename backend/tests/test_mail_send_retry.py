"""Tests for SMTP send retry logic in mail_send_worker."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.workers import mail_send_worker


class MailSendRetryTests(unittest.TestCase):
    def test_bump_retry_increments_counter_in_raw_payload(self) -> None:
        msg = SimpleNamespace(raw_payload={"mail_history_id": 7})
        result = mail_send_worker._bump_retry(msg, "boom")
        self.assertEqual(result, 1)
        self.assertEqual(msg.raw_payload["retries"], 1)
        self.assertEqual(msg.raw_payload["mail_history_id"], 7)
        self.assertEqual(msg.raw_payload["last_error"], "boom")

    def test_bump_retry_starts_from_existing_counter(self) -> None:
        msg = SimpleNamespace(raw_payload={"retries": 2})
        result = mail_send_worker._bump_retry(msg, "again")
        self.assertEqual(result, 3)
        self.assertEqual(msg.raw_payload["retries"], 3)

    def test_send_ready_messages_retries_below_max(self) -> None:
        msg = SimpleNamespace(
            id=42,
            raw_payload={},
            to_emails=["x@y.com"],
            cc_emails=[],
            bcc_emails=[],
            subject="s",
            body="b",
            receiver_email="x@y.com",
            error_message=None,
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [msg]

        with patch.object(mail_send_worker, "SessionLocal", return_value=db):
            with patch.object(
                mail_send_worker, "_config_ready", return_value=(True, "")
            ):
                with patch.object(
                    mail_send_worker, "_send_one", side_effect=RuntimeError("nope")
                ):
                    with patch.object(
                        mail_send_worker,
                        "_sync_delivery_state",
                    ) as sync_delivery:
                        result = mail_send_worker.send_ready_messages(limit=1)

        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["results"][0]["status"], "RETRY")
        self.assertEqual(result["results"][0]["retries"], 1)
        sync_delivery.assert_not_called()

    def test_send_ready_messages_marks_failed_at_threshold(self) -> None:
        msg = SimpleNamespace(
            id=99,
            raw_payload={"retries": 2},
            to_emails=["x@y.com"],
            cc_emails=[],
            bcc_emails=[],
            subject="s",
            body="b",
            receiver_email="x@y.com",
            error_message=None,
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [msg]

        with patch.object(mail_send_worker, "SessionLocal", return_value=db):
            with patch.object(
                mail_send_worker, "_config_ready", return_value=(True, "")
            ):
                with patch.object(
                    mail_send_worker, "_send_one", side_effect=RuntimeError("boom")
                ):
                    with patch.object(
                        mail_send_worker,
                        "_sync_delivery_state",
                    ) as sync_delivery:
                        result = mail_send_worker.send_ready_messages(limit=1)

        self.assertEqual(result["results"][0]["status"], "FAILED")
        sync_delivery.assert_called_once()


if __name__ == "__main__":
    unittest.main()
