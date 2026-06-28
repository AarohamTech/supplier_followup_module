import unittest
from unittest.mock import patch

from app.workers import mail_send_worker as w


class SendHtmlEmailTests(unittest.TestCase):
    def test_skips_when_smtp_not_ready(self):
        with patch.object(w, "_config_ready", return_value=(False, "SMTP_ENABLED is false")):
            result = w.send_html_email(["a@x.com"], "Subj", "<b>hi</b>")
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "SMTP_ENABLED is false")

    def test_skips_when_no_recipients(self):
        with patch.object(w, "_config_ready", return_value=(True, "")):
            result = w.send_html_email([], "Subj", "<b>hi</b>")
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "no recipients")

    def test_sends_html_alternative(self):
        with patch.object(w, "_config_ready", return_value=(True, "")), \
             patch.object(w, "_send_one") as send_one:
            result = w.send_html_email(["a@x.com", "b@y.com"], "Subj", "<b>hi</b>")
        self.assertTrue(result["sent"])
        self.assertEqual(result["recipients"], 2)
        em = send_one.call_args.args[0]
        self.assertEqual(em["Subject"], "Subj")
        self.assertEqual(em["To"], "a@x.com, b@y.com")
        self.assertTrue(em.get_content_type().startswith("multipart"))
