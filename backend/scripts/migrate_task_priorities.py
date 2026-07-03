"""Migrate task/customer-mail priorities from P0-P3 to LOW/MEDIUM/HIGH.

Mapping: P0 -> HIGH, P1 -> HIGH, P2 -> MEDIUM, P3 -> LOW.
Affects communication_tasks.priority and customer_mails.priority.

Run from backend/:
    .venv/Scripts/python.exe -m scripts.migrate_task_priorities          # dry run
    .venv/Scripts/python.exe -m scripts.migrate_task_priorities --yes    # apply
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from app.database import SessionLocal

MAPPING = {"P0": "HIGH", "P1": "HIGH", "P2": "MEDIUM", "P3": "LOW"}
TABLES = ("communication_tasks", "customer_mails")


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        for table in TABLES:
            for old, new in MAPPING.items():
                n = db.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE priority = :old"),
                    {"old": old},
                ).scalar() or 0
                if not n:
                    continue
                print(f"{'APPLY' if apply else 'WOULD UPDATE'}: {table} {old} -> {new} ({n} rows)")
                if apply:
                    db.execute(
                        text(f"UPDATE {table} SET priority = :new WHERE priority = :old"),
                        {"new": new, "old": old},
                    )
        if apply:
            db.commit()
        print("APPLIED" if apply else "DRY RUN (pass --yes to apply)")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--yes" in sys.argv)
