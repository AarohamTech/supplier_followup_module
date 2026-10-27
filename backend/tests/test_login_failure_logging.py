"""Failed sign-ins are logged with the reason (never the password), so a
"users can't sign in" report can be diagnosed from the server log."""
import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_login_log.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.services import user_service  # noqa: E402


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class LoginFailureLoggingTests(unittest.TestCase):
    def test_each_failure_reason_is_logged_without_the_password(self):
        with _temp_db() as db:
            user_service.create_user(db, email="a@x.com", password="right-pw", username="DESK1")
            off = user_service.create_user(db, email="off@x.com", password="pw")
            off.is_active = False
            db.commit()

            with self.assertLogs("app.services.user_service", level="WARNING") as cm:
                self.assertIsNone(user_service.authenticate(db, "nobody@x.com", "secret-1"))
                self.assertIsNone(user_service.authenticate(db, "off@x.com", "secret-2"))
                self.assertIsNone(user_service.authenticate_by_username(db, "desk1", "secret-3"))

        out = "\n".join(cm.output)
        self.assertIn("nobody@x.com", out)
        self.assertIn("unknown account", out)
        self.assertIn("inactive", out)
        self.assertIn("wrong password", out)
        for pw in ("secret-1", "secret-2", "secret-3"):
            self.assertNotIn(pw, out)

    def test_success_is_not_logged_as_failure(self):
        with _temp_db() as db:
            user_service.create_user(db, email="a@x.com", password="right-pw")
            with self.assertNoLogs("app.services.user_service", level="WARNING"):
                self.assertIsNotNone(user_service.authenticate(db, "a@x.com", "right-pw"))


if __name__ == "__main__":
    unittest.main()
