"""Feature 2 — standalone compose service.

Composes an OUTGOING message; validates recipients/subject/body; and every
outgoing mail is delivered in the defined brand HTML format (the send worker
wraps a plain-text body via brand_email).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_compose.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import CommunicationMessage  # noqa: E402,F401
from app.services import compose_service  # noqa: E402
from app.workers import mail_send_worker  # noqa: E402


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


class ComposeServiceTests(unittest.TestCase):
    def test_draft_saved_as_draft_message(self):
        with _temp_db() as db:
            out = compose_service.compose_and_send(
                db,
                to_emails=["vendor@example.com"],
                cc_emails=["cc@example.com", ""],
                subject="Status on PO 000449",
                body="Please share the dispatch date.",
                supplier_name="Vedant Tools Pvt Ltd",
                supplier_po_no="000449",
                send=False,
            )
            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "DRAFT")
            msg = db.get(CommunicationMessage, out["message_id"])
            self.assertEqual(msg.direction, "OUTGOING")
            self.assertEqual(msg.status, "DRAFT")
            self.assertEqual(msg.to_emails, ["vendor@example.com"])
            self.assertEqual(msg.cc_emails, ["cc@example.com"])  # blanks stripped
            self.assertEqual(msg.mail_type, "HUB_COMPOSE")

    def test_validation_requires_recipient_subject_body(self):
        with _temp_db() as db:
            with self.assertRaises(HTTPException):
                compose_service.compose_and_send(db, to_emails=[], subject="s", body="b", send=False)
            with self.assertRaises(HTTPException):
                compose_service.compose_and_send(db, to_emails=["a@b.com"], subject="", body="b", send=False)
            with self.assertRaises(HTTPException):
                compose_service.compose_and_send(db, to_emails=["a@b.com"], subject="s", body="", send=False)

    def test_outgoing_mail_is_brand_html(self):
        with _temp_db() as db:
            out = compose_service.compose_and_send(
                db,
                to_emails=["vendor@example.com"],
                subject="Hello",
                body="Plain text body line.",
                send=False,
            )
            msg = db.get(CommunicationMessage, out["message_id"])
            em = mail_send_worker._build_email(msg)
            # A multipart alternative with an HTML part must be present.
            html_parts = [p for p in em.walk() if p.get_content_type() == "text/html"]
            self.assertTrue(html_parts, "outgoing mail has no HTML part")
            html = html_parts[0].get_content()
            self.assertIn("Plain text body line.", html)
            self.assertIn("<", html)  # actual HTML markup, not plain text

    def test_draft_body_template_fallback(self):
        # AI is disabled in tests → deterministic template with the recipient + PO.
        result = compose_service.draft_body(
            audience="supplier",
            instruction="request an updated commitment date",
            supplier_name="Vedant Tools Pvt Ltd",
            supplier_po_no="000449",
        )
        self.assertIn("source", result)
        self.assertIn("Vedant Tools Pvt Ltd", result["body"])
        self.assertIn("000449", result["body"])


if __name__ == "__main__":
    unittest.main()
