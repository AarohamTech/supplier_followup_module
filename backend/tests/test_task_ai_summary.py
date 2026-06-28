"""AI summary endpoint behaviour (LLM stubbed)."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.core.deps import get_current_staff, get_current_user
from app.models import CommunicationTask, User  # noqa: F401
import app.main as main_mod


@contextmanager
def _client():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    task = CommunicationTask(title="Chase PO", description="Need ETA")
    db.add(task)
    db.commit()
    db.refresh(task)

    fake_actor = User(id=1, email="a@x.com", full_name="Admin", hashed_password="x", role="admin")

    def _get_db():
        yield db

    app = main_mod.app
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_staff] = lambda: fake_actor
    app.dependency_overrides[get_current_user] = lambda: fake_actor
    try:
        yield TestClient(app), db, task
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


class AiSummaryTests(unittest.TestCase):
    def test_generates_and_caches_summary(self) -> None:
        with _client() as (client, db, task):
            with mock.patch("app.services.ai_service.is_enabled", return_value=True), \
                 mock.patch("app.services.ai_service.summarize_thread", return_value="Short summary."):
                r = client.post(f"/api/tasks/{task.id}/ai-summary")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ai_summary"], "Short summary.")
            self.assertEqual(r.json()["ai_summary_by"], "Admin")

    def test_503_when_llm_disabled(self) -> None:
        with _client() as (client, db, task):
            with mock.patch("app.services.ai_service.is_enabled", return_value=False):
                r = client.post(f"/api/tasks/{task.id}/ai-summary")
            self.assertEqual(r.status_code, 503)

    def test_404_when_task_missing(self) -> None:
        with _client() as (client, db, task):
            with mock.patch("app.services.ai_service.is_enabled", return_value=True):
                r = client.post("/api/tasks/999999/ai-summary")
            self.assertEqual(r.status_code, 404)
