import unittest

from app.core.schema_evolve import ensure_columns_in_schema
from app.database import engine


class PerSchemaEvolveTests(unittest.TestCase):
    def test_noop_on_sqlite(self):
        # SQLite has no schemas → must be a safe no-op returning [].
        assert ensure_columns_in_schema(engine, "company_101") == []
