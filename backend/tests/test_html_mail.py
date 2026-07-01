"""Tests for HTML email generation and HTML MIME sending."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.mail_template_service import (
    render_po_materials_table_html,
    render_po_reply_table_html,
    _status_badge,
)
from app.workers import mail_send_worker


SAMPLE_MATERIALS = [
    {
        "crm_no": "CRM-1",
        "material_name": "Steel Rod",
        "po_qty": 10,
        "uom": "NOS",
        "due_date": "2026-06-30",
        "current_status": "DELAYED",
        "commitment": {"commitment_date": "2026-07-05", "supplier_remark": "stock issue"},
    },
    {
        "crm_no": "CRM-2",
        "material_name": "Copper Plate",
        "po_qty": 5,
        "uom": "NOS",
        "due_date": "2026-07-01",
        "current_status": "CONFIRMED",
        "commitment": {},
    },
]


class HtmlMailGenerationTests(unittest.TestCase):
    def test_materials_table_contains_html_table_and_headers(self) -> None:
        html = render_po_materials_table_html(SAMPLE_MATERIALS)
        self.assertIn("<table", html)
        self.assertIn("</table>", html)
        self.assertIn("CRM No", html)
        self.assertIn("Material Name", html)
        self.assertIn("Steel Rod", html)
        # inline CSS present
        self.assertIn("border-collapse", html)

    def test_status_badge_uses_color_for_known_status(self) -> None:
        badge = _status_badge("CONFIRMED")
        self.assertIn("<span", badge)
        self.assertIn("CONFIRMED", badge)

    def test_reply_table_has_all_reply_columns(self) -> None:
        html = render_po_reply_table_html(SAMPLE_MATERIALS)
        for col in ["CRM No", "Material Name", "Qty", "Commitment Date", "Remark", "Status"]:
            self.assertIn(col, html)
        self.assertIn("<table", html)

    def test_empty_materials_table_is_safe(self) -> None:
        self.assertIn("No materials", render_po_materials_table_html([]))


class HtmlMimeSendTests(unittest.TestCase):
    def test_build_email_attaches_html_alternative(self) -> None:
        msg = SimpleNamespace(
            to_emails=["s@x.com"],
            cc_emails=[],
            bcc_emails=[],
            receiver_email="s@x.com",
            subject="PO Follow-up",
            body="Plain body",
            body_html="<table><tr><td>Steel</td></tr></table>",
        )
        with patch.object(mail_send_worker.settings, "SMTP_FROM", "from@x.com"):
            em = mail_send_worker._build_email(msg)
        # The message must be multipart/alternative carrying an HTML part.
        self.assertTrue(em.is_multipart())
        html_parts = [
            p for p in em.walk() if p.get_content_type() == "text/html"
        ]
        self.assertEqual(len(html_parts), 1)
        self.assertIn("<table", html_parts[0].get_content())

    def test_build_email_wraps_plain_body_in_branded_html(self) -> None:
        # Every outgoing mail must leave as HTML: a plain-text body with no authored
        # body_html is wrapped in the branded shell, keeping the text as fallback.
        msg = SimpleNamespace(
            to_emails=["s@x.com"],
            cc_emails=[],
            bcc_emails=[],
            receiver_email="s@x.com",
            subject="Plain",
            body="Just text",
            body_html=None,
        )
        with patch.object(mail_send_worker.settings, "SMTP_FROM", "from@x.com"):
            em = mail_send_worker._build_email(msg)
        self.assertTrue(em.is_multipart())
        html_parts = [p for p in em.walk() if p.get_content_type() == "text/html"]
        self.assertEqual(len(html_parts), 1)
        html = html_parts[0].get_content()
        self.assertIn("Just text", html)          # the body is embedded…
        self.assertIn("Harmony", html)            # …inside the branded shell
        text_parts = [p for p in em.walk() if p.get_content_type() == "text/plain"]
        self.assertIn("Just text", text_parts[0].get_content())

    def test_build_email_escapes_plain_body_html(self) -> None:
        # Arbitrary text must be HTML-escaped when wrapped so it can't inject markup.
        msg = SimpleNamespace(
            to_emails=["s@x.com"], cc_emails=[], bcc_emails=[], receiver_email="s@x.com",
            subject="Plain", body="a < b & <script>x</script>", body_html=None,
        )
        with patch.object(mail_send_worker.settings, "SMTP_FROM", "from@x.com"):
            em = mail_send_worker._build_email(msg)
        html = [p for p in em.walk() if p.get_content_type() == "text/html"][0].get_content()
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_build_email_plain_only_when_no_body_at_all(self) -> None:
        # Nothing to wrap (no body, no html) → stays a simple plain-text message.
        msg = SimpleNamespace(
            to_emails=["s@x.com"], cc_emails=[], bcc_emails=[], receiver_email="s@x.com",
            subject="Empty", body="", body_html=None,
        )
        with patch.object(mail_send_worker.settings, "SMTP_FROM", "from@x.com"):
            em = mail_send_worker._build_email(msg)
        self.assertFalse(em.is_multipart())

    def test_html_to_text_strips_tags(self) -> None:
        text = mail_send_worker._html_to_text("<p>Hello</p><table><tr><td>X</td></tr></table>")
        self.assertIn("Hello", text)
        self.assertNotIn("<", text)


if __name__ == "__main__":
    unittest.main()
