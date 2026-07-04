"""Tests for `seed.ensure_company_schemas`: creates the Postgres schema + tables
for every non-public company on startup. No-op on SQLite (tests stay green).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

# Force a throwaway SQLite DB before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_seed_company_schema.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import seed  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import company_service  # noqa: E402


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


class EnsureCompanySchemasTests(unittest.TestCase):
    def test_noop_on_sqlite(self):
        with _temp_db() as db:
            company_service.seed_companies(db)
            self.assertEqual(seed.ensure_company_schemas(db), [])


if __name__ == "__main__":
    unittest.main()
