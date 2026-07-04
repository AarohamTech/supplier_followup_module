"""Regression guard: the app's shared DB engine must be SQLite during tests.

If this ever fails, a test run is bound to a real database (production is in
`backend/.env`). `tests/conftest.py` forces `DATABASE_URL=sqlite:///...` before
any `app.*` import to prevent exactly that; this test proves it stuck.
"""
from app.database import engine


def test_app_engine_is_sqlite_during_tests():
    backend = engine.url.get_backend_name()
    assert backend.startswith("sqlite"), f"app engine bound to {backend!r} — NOT SQLite: {engine.url}"
