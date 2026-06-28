"""One-time remap of free-text task assignees to real user ids.

Run from backend/ on the Mumbai box:
    .venv/Scripts/python.exe -m scripts.remap_task_assignees          # dry run
    .venv/Scripts/python.exe -m scripts.remap_task_assignees --yes    # apply
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.communication_task import CommunicationTask
from app.models.user import User
from app import seed
from app.services import task_assignment_service as assign


def _name_index(db) -> dict[str, int]:
    idx: dict[str, int] = {}
    users = db.scalars(
        select(User).where(User.is_active.is_(True), User.supplier_id.is_(None))
    ).all()
    for u in users:
        for key in filter(None, [u.full_name, u.username, u.email]):
            idx[key.strip().lower()] = u.id
    return idx


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        roles = seed.ensure_role_accounts(db)
        print(f"role accounts: {roles}")
        idx = _name_index(db)

        tasks = db.scalars(select(CommunicationTask)).all()
        matched = unmatched = already = 0
        unmatched_names: set[str] = set()

        for t in tasks:
            if t.assigned_to_user_id:
                already += 1
                continue
            name = (t.assigned_to or "").strip().lower()
            uid = idx.get(name)
            if uid:
                if apply:
                    user = db.get(User, uid)
                    t.assigned_to_user_id = uid
                    t.assigned_to = assign.display_name(user)
                matched += 1
            elif name:
                unmatched += 1
                unmatched_names.add(t.assigned_to)

        if apply:
            db.commit()
        print(f"tasks={len(tasks)} already_mapped={already} matched={matched} unmatched={unmatched}")
        if unmatched_names:
            print("unmatched assignee strings (left as-is):")
            for n in sorted(unmatched_names):
                print(f"  - {n}")
        print("APPLIED" if apply else "DRY RUN (pass --yes to apply)")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--yes" in sys.argv)
