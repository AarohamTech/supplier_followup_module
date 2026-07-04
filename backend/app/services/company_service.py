"""Company (tenant) registry: seeding, lookups, and a small in-process cache
mapping the JWT `company` code to a Postgres schema. No FastAPI imports."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.tenant import DEFAULT_SCHEMA
from ..models.company import Company

# Canonical company definitions. 102 keeps the current data in `public`; 101 is new.
SEED_COMPANIES: list[dict] = [
    dict(code="102", display_name="Hariom Tech", schema_name="public",
         theme="red", brand_name="H-Connect", is_active=True, is_default=True),
    dict(code="101", display_name="Enterprise", schema_name="company_101",
         theme="blue", brand_name="Enterprise", is_active=True, is_default=False),
]

# code -> schema_name; refreshed from the DB. Read on the hot request path so the
# tenant middleware never issues a query per request.
_schema_cache: dict[str, str] = {}
_default_schema: str = DEFAULT_SCHEMA


def seed_companies(db: Session) -> dict:
    created = 0
    existing = 0
    for spec in SEED_COMPANIES:
        row = db.scalar(select(Company).where(Company.code == spec["code"]))
        if row is None:
            db.add(Company(**spec))
            created += 1
        else:
            existing += 1
    db.commit()
    refresh_cache(db)
    return {"created": created, "existing": existing}


def refresh_cache(db: Session) -> None:
    global _default_schema
    rows = list(db.scalars(select(Company)).all())
    _schema_cache.clear()
    for row in rows:
        _schema_cache[row.code] = row.schema_name
        if row.is_default:
            _default_schema = row.schema_name


def get_schema_for_code(code: str | None) -> str:
    if not code:
        return _default_schema
    return _schema_cache.get(code, _default_schema)


def list_active(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).where(Company.is_active.is_(True))
                           .order_by(Company.code)).all())


def get_by_code(db: Session, code: str) -> Company | None:
    return db.scalar(select(Company).where(Company.code == code))


def get_default(db: Session) -> Company | None:
    return db.scalar(select(Company).where(Company.is_default.is_(True)))
