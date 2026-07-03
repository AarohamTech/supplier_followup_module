"""Tests for task comments and activity logging."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CommunicationTask, TaskActivityLog, TaskComment  # noqa: F401
from app.services import task_collaboration_service as collab


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


def _make_task(db) -> CommunicationTask:
    task = CommunicationTask(title="Follow up PO", status="TODO", priority="MEDIUM", signal="YELLOW")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


class TaskCommentTests(unittest.TestCase):
    def test_add_comment_increments_counter_and_logs_activity(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            comment = collab.add_comment(
                db, task_id=task.id, comment="Called supplier", created_by="ops"
            )
            self.assertEqual(comment.comment, "Called supplier")

            db.refresh(task)
            self.assertEqual(task.comments_count, 1)

            comments = collab.list_comments(db, task.id)
            self.assertEqual(len(comments), 1)

            activity = collab.list_activity(db, task.id)
            self.assertTrue(any(a.activity_type == "COMMENT_ADDED" for a in activity))

    def test_add_comment_unknown_task_raises(self) -> None:
        with _temp_db() as db:
            with self.assertRaises(ValueError):
                collab.add_comment(db, task_id=999, comment="x")


class TaskActivityTests(unittest.TestCase):
    def test_record_task_changes_only_logs_changed_fields(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            entries = collab.record_task_changes(
                db,
                task,
                {
                    "status": ("TODO", "IN_PROGRESS"),
                    "priority": ("MEDIUM", "MEDIUM"),  # unchanged → ignored
                    "assigned_to": (None, "alice"),
                },
            )
            db.commit()
            types = {e.activity_type for e in entries}
            self.assertIn("STATUS_CHANGED", types)
            self.assertIn("ASSIGNEE_CHANGED", types)
            self.assertNotIn("PRIORITY_CHANGED", types)

    def test_log_activity_truncates_long_values(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            entry = collab.log_activity(
                db,
                task_id=task.id,
                activity_type="STATUS_CHANGED",
                new_value="x" * 1000,
                commit=True,
            )
            self.assertLessEqual(len(entry.new_value), 500)


class TaskCollabExtrasTests(unittest.TestCase):
    def test_progress_change_logged_with_actor_id(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            entries = collab.record_task_changes(
                db, task, {"progress_percent": (0, 50)}, created_by="ops", created_by_id=9
            )
            db.commit()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].activity_type, "PROGRESS_CHANGED")
            self.assertEqual(entries[0].created_by_id, 9)

    def test_comment_stores_actor_id(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            c = collab.add_comment(
                db, task_id=task.id, comment="hi", created_by="ops", created_by_id=9
            )
            self.assertEqual(c.created_by_id, 9)

    def test_build_transcript_includes_desc_comments_activity(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            task.description = "Chase the PO"
            db.commit()
            collab.add_comment(db, task_id=task.id, comment="Called supplier", created_by="ops")
            collab.record_task_changes(db, task, {"status": ("TODO", "IN_PROGRESS")})
            db.commit()
            text = collab.build_transcript(db, task)
            self.assertIn("Chase the PO", text)
            self.assertIn("Called supplier", text)
            self.assertIn("IN_PROGRESS", text)


if __name__ == "__main__":
    unittest.main()
