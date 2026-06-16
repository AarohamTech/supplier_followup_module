from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from .core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# When DB_SCHEMA is set (Postgres only), pin the connection's search_path to it
# so every unqualified table lives in that schema — isolating this app from any
# other tables sharing the database.
_schema = (settings.DB_SCHEMA or "").strip() or None

connect_args: dict = {}
if _is_sqlite:
    connect_args = {"check_same_thread": False}
elif _schema:
    connect_args = {"options": f"-csearch_path={_schema}"}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def ensure_schema() -> str | None:
    """Create the configured schema if it does not exist. No-op for SQLite or
    when DB_SCHEMA is unset. Safe to call repeatedly. Returns the schema name."""
    if _is_sqlite or not _schema:
        return None
    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{_schema}"'))
        conn.commit()
    return _schema


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
