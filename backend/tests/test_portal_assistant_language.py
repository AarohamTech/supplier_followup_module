"""Supplier assistant answers in the portal's language.

The portal sends `language: "mr"` when the supplier uses it in Marathi; the
endpoint then adds a fixed "reply in Marathi" rule to the assistant's
instructions. English, a missing value or any other value leave the
instructions unchanged, and the value itself never reaches the prompt.
The LLM call is replaced by a stub (no network, no API key).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_portal_assistant_language.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import SupplierMaster, User  # noqa: E402,F401
from app.routers import portal  # noqa: E402


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


def _supplier_user(db) -> User:
    s = SupplierMaster(supplier_name="M/S SUPERB TOOLS", is_active=True)
    db.add(s)
    db.commit()
    u = User(email="orders@superb.example", hashed_password="x", role="supplier", supplier_id=s.id, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class AssistantLanguageTests(unittest.TestCase):
    def _ask(self, language=None, **extra):
        """Call the endpoint with a stub LLM; return the system prompt it was given."""
        seen: dict = {}

        def fake_chat(messages, *, tools, executor, system):
            seen["system"] = system
            seen["messages"] = messages
            return {"reply": "ok", "tools_used": []}

        body = {"messages": [{"role": "user", "content": "Status of my latest PO?"}], **extra}
        if language is not None:
            body["language"] = language
        payload = portal._AssistantRequest(**body)
        with _temp_db() as db, \
                mock.patch.object(portal.ai_service, "any_enabled", return_value=True), \
                mock.patch.object(portal.ai_service, "active_model", return_value="stub-model"), \
                mock.patch.object(portal.ai_service, "chat_with_tools", side_effect=fake_chat):
            out = portal.assistant_chat(payload, user=_supplier_user(db), db=db)
        self.assertEqual(out["reply"], "ok")
        return seen

    def test_marathi_adds_reply_in_marathi_rule(self):
        seen = self._ask("mr")
        self.assertIn("Reply in Marathi", seen["system"])
        self.assertTrue(seen["system"].endswith(portal._MARATHI_REPLY_RULE))
        # Scope rules are still there, and the question is passed through as-is.
        self.assertIn("M/S SUPERB TOOLS", seen["system"])
        self.assertIn("never another supplier", seen["system"])
        self.assertEqual(seen["messages"], [{"role": "user", "content": "Status of my latest PO?"}])

    def test_marathi_value_is_case_and_space_tolerant(self):
        self.assertIn("Reply in Marathi", self._ask(" MR ")["system"])

    def test_english_missing_or_other_values_keep_prompt_unchanged(self):
        baseline = self._ask()["system"]
        self.assertNotIn("Marathi", baseline)
        for value in ("en", "", "hi", "fr"):
            with self.subTest(language=value):
                self.assertEqual(self._ask(value)["system"], baseline)

    def test_language_value_is_never_copied_into_prompt(self):
        # Even a value shaped like an instruction is only compared, never inserted.
        sneaky = "mr!x"
        system = self._ask(sneaky)["system"]
        self.assertNotIn(sneaky, system)
        self.assertNotIn("Marathi", system)

    def test_overlong_language_value_is_rejected(self):
        with self.assertRaises(Exception):
            portal._AssistantRequest(messages=[{"role": "user", "content": "hi"}], language="mr" * 20)

    def test_empty_messages_still_rejected(self):
        with _temp_db() as db:
            with self.assertRaises(HTTPException) as cm:
                portal.assistant_chat(portal._AssistantRequest(messages=[], language="mr"), user=_supplier_user(db), db=db)
        self.assertEqual(cm.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
