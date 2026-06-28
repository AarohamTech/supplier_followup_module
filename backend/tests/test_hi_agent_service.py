"""Tests for the HI-agent orchestrator."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AgentSubscription, CommunicationMessage  # noqa: F401
from app.models.communication_message import CommunicationMessage as CM
from app.services import hi_agent_service as agent


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


def _seed(db):
    db.add(CM(
        direction="INCOMING", status="RECEIVED", channel="EMAIL",
        procurement_record_id=10, supplier_po_no="PO-1",
        subject="Re: PO-1", body="Dispatching 5 July.",
    ))
    db.commit()


class OrchestratorTests(unittest.TestCase):
    def test_fallback_summarises_when_llm_disabled(self) -> None:
        with _temp_db() as db:
            _seed(db)
            with patch("app.services.hi_agent_service.ai_service.is_enabled", return_value=False):
                out = agent.run(
                    db, user=None, message="summarise this",
                    supplier_id=1, procurement_record_id=10, supplier_po_no="PO-1",
                )
            self.assertIn("5 July", out["reply"])
            self.assertEqual(out["pending_actions"], [])

    def test_fallback_help_for_unknown_when_llm_disabled(self) -> None:
        with _temp_db() as db:
            _seed(db)
            with patch("app.services.hi_agent_service.ai_service.is_enabled", return_value=False):
                out = agent.run(
                    db, user=None, message="do a barrel roll",
                    supplier_id=1, procurement_record_id=10, supplier_po_no="PO-1",
                )
            self.assertIn("can", out["reply"].lower())

    def test_uses_chat_with_tools_when_llm_enabled(self) -> None:
        with _temp_db() as db:
            _seed(db)

            def fake_chat_with_tools(messages, *, tools, executor, system, max_rounds=None):
                executor("summarize_thread", {})
                return {"reply": "Here is your summary.", "tools_used": [{"name": "summarize_thread"}]}

            with patch("app.services.hi_agent_service.ai_service.is_enabled", return_value=True), \
                 patch("app.services.hi_agent_service.ai_service.chat_with_tools",
                       side_effect=fake_chat_with_tools):
                out = agent.run(
                    db, user=None, message="summarise + send to @anjali",
                    supplier_id=1, procurement_record_id=10, supplier_po_no="PO-1",
                )
            self.assertEqual(out["reply"], "Here is your summary.")
            self.assertEqual(out["tools_used"], [{"name": "summarize_thread"}])
