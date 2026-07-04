"""Tests for user.company_id column: pins portal accounts to a company.

DB-backed with an in-memory SQLite (production data untouched).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

# Force a throwaway SQLite DB before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_user_company_id.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import Base  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.company import Company  # noqa: E402


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


class UserCompanyIdTests(unittest.TestCase):
    def test_staff_account_has_no_company_id(self):
        """Staff accounts (company_id NULL) are not pinned to any company."""
        with _temp_db() as db:
            user = User(email="staff@example.com", hashed_password="x", role="admin")
            db.add(user)
            db.commit()

            # Re-select by email to verify round-trip
            row = db.execute(select(User).filter(User.email == "staff@example.com")).scalar_one()
            self.assertIsNone(row.company_id)

    def test_portal_account_pinned_to_company(self):
        """Portal accounts can be pinned to a specific company via company_id FK."""
        with _temp_db() as db:
            # Create a company first
            company = Company(
                code="101",
                display_name="Enterprise",
                schema_name="company_101",
            )
            db.add(company)
            db.commit()
            db.refresh(company)

            # Create a portal user pinned to that company
            user = User(
                email="portal@example.com",
                hashed_password="y",
                role="supplier",
                company_id=company.id,
            )
            db.add(user)
            db.commit()

            # Re-select to verify round-trip
            row = db.execute(select(User).filter(User.email == "portal@example.com")).scalar_one()
            self.assertEqual(row.company_id, company.id)


if __name__ == "__main__":
    unittest.main()
