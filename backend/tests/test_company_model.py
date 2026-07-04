"""Tests for the `Company` (tenant registry) model.

DB-backed with an in-memory SQLite, matching the repo's unittest.TestCase pattern
(see test_supplier_portal.py) — no pytest fixtures / conftest reliance.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

# Force a throwaway SQLite DB before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_company_model.sqlite")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models.company import Company  # noqa: E402,F401 — ensures table is registered


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


class TestCompanyModel(unittest.TestCase):
    def test_insert_and_query_company(self):
        with _temp_db() as db:
            company = Company(
                code="102",
                display_name="Hariom Tech",
                schema_name="public",
                theme="red",
                brand_name="H-Connect",
                is_active=True,
                is_default=True,
            )
            db.add(company)
            db.commit()

            row = db.execute(
                select(Company).where(Company.code == "102")
            ).scalar_one_or_none()

            self.assertIsNotNone(row)
            self.assertEqual(row.schema_name, "public")
            self.assertEqual(row.theme, "red")
            self.assertIs(row.is_default, True)
            self.assertIs(row.is_active, True)


if __name__ == "__main__":
    unittest.main()
