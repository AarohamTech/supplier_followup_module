import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_tenant_middleware.sqlite")

import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.core.security import create_access_token
from app.core.tenant_middleware import schema_from_authorization
from app.services import company_service


class SchemaFromAuthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool, future=True)
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        company_service.seed_companies(self.db)
        company_service.refresh_cache(self.db)

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_resolves_company(self):
        token = create_access_token(subject=1, role="admin", extra={"company": "101"})
        self.assertEqual(schema_from_authorization(f"Bearer {token}"), "company_101")

    def test_defaults_on_missing_or_bad(self):
        self.assertEqual(schema_from_authorization(None), "public")
        self.assertEqual(schema_from_authorization("Bearer not-a-jwt"), "public")
        t = create_access_token(subject=1, role="admin")
        self.assertEqual(schema_from_authorization(f"Bearer {t}"), "public")


if __name__ == "__main__":
    unittest.main()
