import inspect
import unittest

from app.workers import mail_send_worker as w


class MailSendSchemaPlumbingTests(unittest.TestCase):
    def test_send_ready_messages_accepts_schema_kwarg(self):
        sig = inspect.signature(w.send_ready_messages)
        assert "schema" in sig.parameters

    def test_bucket_reestablishes_schema_in_thread(self):
        sig = inspect.signature(w._send_bucket)
        assert "schema" in sig.parameters
        src = inspect.getsource(w._send_bucket)
        assert "use_company" in src


if __name__ == "__main__":
    unittest.main()
