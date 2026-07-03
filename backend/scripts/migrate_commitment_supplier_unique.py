"""Migrate supplier_material_commitments unique key to include supplier_name.

CRM PoNo is a recycled counter shared across suppliers, so the commitment
identity must be (supplier_name, supplier_po_no, material_name). The app creates
tables with Base.metadata.create_all (no Alembic), which does NOT alter an
existing constraint — so this one-off script performs the ALTER on Postgres.

The change is strictly more permissive (adds a column to the key), so no
existing rows can be invalidated and no dedup is required.

Run from backend/ (Postgres/prod):
    .venv/Scripts/python.exe -m scripts.migrate_commitment_supplier_unique          # dry run
    .venv/Scripts/python.exe -m scripts.migrate_commitment_supplier_unique --yes    # apply
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from app.database import SessionLocal, engine

OLD_NAME = "uq_commitment_po_material"
NEW_NAME = "uq_commitment_supplier_po_material"
TABLE = "supplier_material_commitments"


def _constraint_exists(db, name: str) -> bool:
    row = db.execute(
        text(
            "SELECT 1 FROM pg_constraint WHERE conname = :name "
            "AND conrelid = :tbl::regclass"
        ),
        {"name": name, "tbl": TABLE},
    ).first()
    return row is not None


def main(apply: bool) -> None:
    if engine.dialect.name != "postgresql":
        print(f"dialect={engine.dialect.name}: nothing to do (create_all builds the new key).")
        return

    db = SessionLocal()
    try:
        has_old = _constraint_exists(db, OLD_NAME)
        has_new = _constraint_exists(db, NEW_NAME)
        print(f"table={TABLE} has_old={has_old} has_new={has_new}")

        if has_new and not has_old:
            print("Already migrated. Nothing to do.")
            return

        stmts: list[str] = []
        if has_old:
            stmts.append(f"ALTER TABLE {TABLE} DROP CONSTRAINT {OLD_NAME}")
        if not has_new:
            stmts.append(
                f"ALTER TABLE {TABLE} ADD CONSTRAINT {NEW_NAME} "
                f"UNIQUE (supplier_name, supplier_po_no, material_name)"
            )

        for s in stmts:
            print(("APPLY: " if apply else "WOULD RUN: ") + s)
            if apply:
                db.execute(text(s))
        if apply:
            db.commit()
        print("APPLIED" if apply else "DRY RUN (pass --yes to apply)")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--yes" in sys.argv)
