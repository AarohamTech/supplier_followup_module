"""Tests for SMTP send retry logic in mail_send_worker."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import CommunicationMessage
from app.services import communication_message_service as msg_service
from app.services.mail_config_service import SmtpConfig
from app.workers import mail_send_worker


def _ready_cfg() -> SmtpConfig:
    # host + from present, user/password both empty → a usable (ready) config.
    return SmtpConfig(enabled=True, host="smtp.test", port=587, user="", password="", from_addr="from")


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


class SendReadyRetryPathTests(unittest.TestCase):
    """Drive send_ready_messages end-to-end against a real in-memory DB with a
    failing SMTP client, exercising the RETRY-below-max and FAILED-at-threshold
    branches of the new per-message send path."""

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def _queue(self, retries: int = 0) -> int:
        db = self.Session()
        try:
            msg = msg_service.queue_outgoing_message(
                db, to_emails=["x@y.com"], subject="s", body="b", commit=True
            )
            if retries:
                msg.raw_payload = {"retries": retries}
                db.commit()
            return msg.id
        finally:
            db.close()

    def _run_with_failing_smtp(self):
        client = MagicMock()
        client.send_message.side_effect = RuntimeError("nope")
        with patch.object(mail_send_worker, "SessionLocal", self.Session), \
             patch.object(mail_send_worker.mail_config_service, "get_smtp_config", return_value=_ready_cfg()), \
             patch.object(mail_send_worker, "_open_client", return_value=client):
            return mail_send_worker.send_ready_messages(limit=1)

    def test_send_ready_messages_retries_below_max(self) -> None:
        mid = self._queue()
        result = self._run_with_failing_smtp()
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["results"][0]["status"], "RETRY")
        self.assertEqual(result["results"][0]["retries"], 1)
        db = self.Session()
        try:
            self.assertEqual(db.get(CommunicationMessage, mid).status, "READY")  # left for cron
        finally:
            db.close()

    def test_send_ready_messages_marks_failed_at_threshold(self) -> None:
        mid = self._queue(retries=2)  # next bump → 3 == MAX_SEND_RETRIES
        result = self._run_with_failing_smtp()
        self.assertEqual(result["results"][0]["status"], "FAILED")
        db = self.Session()
        try:
            self.assertEqual(db.get(CommunicationMessage, mid).status, "FAILED")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
