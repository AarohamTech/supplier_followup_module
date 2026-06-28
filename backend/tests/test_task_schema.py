"""The new Jira-like columns exist on the ORM models."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CommunicationTask, TaskActivityLog, TaskComment  # noqa: F401
from app.models.task_collaboration import TASK_ACTIVITY_TYPES


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


class TaskSchemaTests(unittest.TestCase):
    def test_new_task_columns_persist(self) -> None:
        with _temp_db() as db:
            t = CommunicationTask(
                title="x", assigned_to_user_id=7, progress_percent=40,
                ai_summary="hi", ai_summary_by="ops",
            )
            db.add(t)
            db.commit()
            db.refresh(t)
            self.assertEqual(t.assigned_to_user_id, 7)
            self.assertEqual(t.progress_percent, 40)
            self.assertEqual(t.ai_summary, "hi")
            self.assertIsNone(t.assigned_at)

    def test_progress_default_zero(self) -> None:
        with _temp_db() as db:
            t = CommunicationTask(title="x")
            db.add(t)
            db.commit()
            db.refresh(t)
            self.assertEqual(t.progress_percent, 0)

    def test_collaboration_actor_id_columns(self) -> None:
        with _temp_db() as db:
            t = CommunicationTask(title="x")
            db.add(t)
            db.commit()
            c = TaskComment(task_id=t.id, comment="c", created_by_id=3)
            a = TaskActivityLog(task_id=t.id, activity_type="PROGRESS_CHANGED", created_by_id=3)
            db.add_all([c, a])
            db.commit()
            self.assertEqual(c.created_by_id, 3)
            self.assertEqual(a.created_by_id, 3)

    def test_activity_vocab_extended(self) -> None:
        self.assertIn("PROGRESS_CHANGED", TASK_ACTIVITY_TYPES)
        self.assertIn("AI_SUMMARY_GENERATED", TASK_ACTIVITY_TYPES)

    def test_out_schema_tolerates_legacy_string_watchers(self) -> None:
        from app.schemas.communication_task import CommunicationTaskOut
        with _temp_db() as db:
            t = CommunicationTask(title="x", watchers=["Sourcing Head", 5])
            db.add(t)
            db.commit()
            db.refresh(t)
            out = CommunicationTaskOut.model_validate(t)
            self.assertEqual(out.watchers, [5])
