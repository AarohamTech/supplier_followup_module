"""Tests for the SMTP send retry counter in mail_send_worker."""
import unittest
from types import SimpleNamespace

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


if __name__ == "__main__":
    unittest.main()
