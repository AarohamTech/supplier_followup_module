"""Tests for the DB-layer tenant switch: SHARED_TABLES + create_company_schema.

DB-backed with a throwaway SQLite DB (production data untouched). SQLite has no
schemas, so `create_company_schema` is a no-op there — these tests verify the
SQLite guard and input validation, not the Postgres DDL itself.

IMPORTANT: `app.database` reads `settings.DATABASE_URL` (via a process-wide,
`lru_cache`d `Settings()`) exactly once, at first import, to compute the
module-level `_is_sqlite` flag and build `engine`. Whichever test module the
pytest session happens to import first "wins" that decision — and several test
modules in this suite import `app.*` without first forcing a throwaway SQLite
`DATABASE_URL` (unlike this file). When one of those imports first, `_is_sqlite`
ends up bound to whatever `backend/.env` really points at (in this repo,
production Supabase — see docs/progress.md), for the rest of the pytest
process, regardless of what this file sets. So the "SQLite no-op" behavior
below is asserted by *patching* `app.database._is_sqlite` directly rather than
relying on it already being True — this test must never execute real DDL
against a real database no matter what ran before it in the same session.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

# Force a throwaway SQLite DB before importing app modules. This only takes
# effect if this is the first module in the pytest session to import app.*;
# see the module docstring above for why the tests below don't rely on it.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_company_schema_ddl.sqlite")

import app.database as database  # noqa: E402
from app.database import SHARED_TABLES, create_company_schema  # noqa: E402


class TestSharedTables(unittest.TestCase):
    def test_shared_tables_are_users_and_companies(self):
        self.assertEqual(SHARED_TABLES, {"users", "companies"})


class TestCreateCompanySchema(unittest.TestCase):
    def test_sqlite_noop_for_company_schema(self):
        # Force the SQLite branch explicitly (see module docstring): this must
        # never fall through to real engine DDL regardless of import order.
        with patch.object(database, "_is_sqlite", True):
            self.assertEqual(create_company_schema("company_101"), [])

    def test_sqlite_noop_for_public_schema(self):
        with patch.object(database, "_is_sqlite", True):
            self.assertEqual(create_company_schema("public"), [])

    def test_invalid_schema_name_raises_value_error(self):
        # Validation runs before any DB/dialect check, so this is safe
        # regardless of `_is_sqlite`.
        with self.assertRaises(ValueError):
            create_company_schema("bad-name; DROP TABLE users")


if __name__ == "__main__":
    unittest.main()
