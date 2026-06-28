"""Seeding the escalation role accounts as real users."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User  # noqa: F401
from app import seed


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


class SeedRoleTests(unittest.TestCase):
    def test_ensure_role_accounts_idempotent(self) -> None:
        with _temp_db() as db:
            m1 = seed.ensure_role_accounts(db)
            m2 = seed.ensure_role_accounts(db)
            self.assertEqual(set(m1), {"Purchase Head", "Sourcing Head"})
            self.assertEqual(m1, m2)  # same ids on re-run
            users = db.scalars(select(User).where(User.full_name == "Purchase Head")).all()
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0].role, "manager")
