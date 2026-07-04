"""Per-request / per-job tenant (company) context.

The active company's Postgres schema is stored in a ContextVar so the DB layer
can pin `search_path` for the current request or background-job iteration. On
SQLite (tests) schemas don't exist, so the value is tracked but never applied.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

DEFAULT_SCHEMA = "public"

_current_schema: ContextVar[str] = ContextVar("current_schema", default=DEFAULT_SCHEMA)


def get_current_schema() -> str:
    return _current_schema.get()


def set_current_schema(schema: str | None) -> Token:
    """Set the active schema; returns a token for `reset_current_schema`."""
    return _current_schema.set(schema or DEFAULT_SCHEMA)


def reset_current_schema(token: Token) -> None:
    _current_schema.reset(token)


@contextmanager
def use_company(schema: str | None) -> Iterator[None]:
    """Bind the active schema for the duration of the block (background jobs)."""
    token = set_current_schema(schema)
    try:
        yield
    finally:
        reset_current_schema(token)
