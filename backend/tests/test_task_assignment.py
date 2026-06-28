"""Assignee resolution: staff + employees only, with display name + actor stamp."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CommunicationTask, User  # noqa: F401
from app.services import task_assignment_service as assign


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


def _user(db, **kw):
    defaults = dict(email=None, username=None, full_name=None, hashed_password="x",
                    role="user", is_active=True, supplier_id=None, emp_code=None)
    defaults.update(kw)
    # The users table requires a non-null email; generate a synthetic placeholder
    # for employee accounts that log in by username only (matches live behaviour
    # where synthetic emails are created for CRM-imported employees).
    if defaults["email"] is None:
        tag = defaults.get("username") or defaults.get("full_name") or "user"
        defaults["email"] = f"{tag.lower().replace(' ', '_')}@synthetic.internal"
    u = User(**defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class AssigneeTests(unittest.TestCase):
    def test_list_excludes_suppliers_and_inactive(self) -> None:
        with _temp_db() as db:
            _user(db, email="staff@x.com", full_name="Staff One", role="manager")
            _user(db, username="PRAMOD", full_name="Pramod", role="employee", emp_code="1010")
            _user(db, email="sup@x.com", full_name="Sup", role="supplier", supplier_id=5)
            _user(db, email="off@x.com", full_name="Off", role="user", is_active=False)
            rows = assign.list_assignees(db)
            labels = {r["label"] for r in rows}
            self.assertEqual(labels, {"Staff One", "Pramod"})
            types = {r["label"]: r["type"] for r in rows}
            self.assertEqual(types["Pramod"], "employee")
            self.assertEqual(types["Staff One"], "staff")

    def test_resolve_returns_display_name(self) -> None:
        with _temp_db() as db:
            u = _user(db, email="s@x.com", full_name="Jane Doe", role="user")
            got, name = assign.resolve_assignee(db, u.id)
            self.assertEqual(got.id, u.id)
            self.assertEqual(name, "Jane Doe")

    def test_resolve_rejects_supplier(self) -> None:
        with _temp_db() as db:
            u = _user(db, email="sup@x.com", full_name="Sup", role="supplier", supplier_id=5)
            with self.assertRaises(ValueError):
                assign.resolve_assignee(db, u.id)

    def test_display_name_falls_back(self) -> None:
        with _temp_db() as db:
            u = _user(db, username="PRAMOD", role="employee", emp_code="1010")
            self.assertEqual(assign.display_name(u), "PRAMOD")

    def test_resolve_rejects_inactive(self) -> None:
        with _temp_db() as db:
            u = _user(db, email="off@x.com", full_name="Off", role="user", is_active=False)
            with self.assertRaises(ValueError):
                assign.resolve_assignee(db, u.id)
