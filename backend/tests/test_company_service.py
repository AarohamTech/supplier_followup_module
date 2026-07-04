"""Tests for company service: seeding, cache, and lookups.

DB-backed with an in-memory SQLite (test isolation).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

# Force a throwaway SQLite DB before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_company_service.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.tenant import DEFAULT_SCHEMA  # noqa: E402
from app.database import Base  # noqa: E402
from app.models.company import Company  # noqa: E402
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


class CompanyServiceTests(unittest.TestCase):
    def test_idempotent_seed(self):
        """Seed twice; first creates 2, second creates 0."""
        with _temp_db() as db:
            result1 = company_service.seed_companies(db)
            self.assertEqual(result1["created"], 2)
            self.assertEqual(result1["existing"], 0)

            result2 = company_service.seed_companies(db)
            self.assertEqual(result2["created"], 0)
            self.assertEqual(result2["existing"], 2)

            # list_active includes both
            active = company_service.list_active(db)
            codes = {c.code for c in active}
            self.assertTrue({"101", "102"}.issubset(codes))

    def test_default_company(self):
        """After seeding, 102 is the default."""
        with _temp_db() as db:
            company_service.seed_companies(db)

            default = company_service.get_default(db)
            self.assertIsNotNone(default)
            self.assertEqual(default.code, "102")
            self.assertEqual(default.schema_name, "public")
            self.assertTrue(default.is_default)

    def test_cache_resolution(self):
        """Cache correctly maps code -> schema_name."""
        with _temp_db() as db:
            company_service.seed_companies(db)

            self.assertEqual(company_service.get_schema_for_code("101"), "company_101")
            self.assertEqual(company_service.get_schema_for_code("102"), "public")
            self.assertEqual(company_service.get_schema_for_code("999"), DEFAULT_SCHEMA)
            self.assertEqual(company_service.get_schema_for_code(None), DEFAULT_SCHEMA)


if __name__ == "__main__":
    unittest.main()
