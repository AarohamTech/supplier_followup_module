"""Smoke test: the AgentSubscription model is registered and its table builds."""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models import AgentSubscription  # noqa: F401


class AgentSubscriptionModelTests(unittest.TestCase):
    def test_table_is_created_with_expected_columns(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        cols = {c["name"] for c in inspect(engine).get_columns("agent_subscriptions")}
        engine.dispose()
        expected = {
            "id", "kind", "supplier_id", "procurement_record_id", "supplier_po_no",
            "recipient_user_id", "recipient_email", "recipient_label",
            "created_by_user_id", "status", "last_forwarded_message_id",
            "schedule", "next_run_at", "last_run_at", "created_at", "updated_at",
        }
        self.assertTrue(expected.issubset(cols), f"missing: {expected - cols}")
