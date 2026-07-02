"""One-time purge of sample/random POs and all their related data.

Wipes every PO, conversation, mail, commitment, ASN, task, notification and the
supplier directory — leaving the system clean for live CRM ingestion to refill.

Preserves: staff + employee user accounts, engine_jobs/logs, app_settings,
mail_parse_rules, mail_templates (config). Supplier-portal logins are removed
along with the suppliers they belong to (a `users.supplier_id` FK requires this,
and an orphaned supplier login is unsafe) — staff and employee accounts stay.

Usage (from the backend/ dir, with its .env / venv):
    python scripts/purge_sample_data.py            # dry run (counts only)
    python scripts/purge_sample_data.py --yes      # actually delete
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the backend root (parent of this scripts/ dir) importable as `app`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.ai_feedback import AIFeedback  # noqa: E402
from app.models.asn import Asn, AsnEvent, AsnItem  # noqa: E402
from app.models.communication_message import CommunicationMessage  # noqa: E402
from app.models.communication_task import CommunicationTask  # noqa: E402
from app.models.customer_mail import CustomerMail  # noqa: E402
from app.models.followup_attempt import FollowupAttempt  # noqa: E402
from app.models.hi_agent_chat_message import HiAgentChatMessage  # noqa: E402
from app.models.mail_history import MailHistory  # noqa: E402
from app.models.mail_parse_rule import MailParseRule  # noqa: E402
from app.models.notification import Notification  # noqa: E402
from app.models.procurement import ProcurementRecord  # noqa: E402
from app.models.status_change_log import StatusChangeLog  # noqa: E402
from app.models.supplier import SupplierMaster  # noqa: E402
from app.models.supplier_email import SupplierEmail  # noqa: E402
from app.models.supplier_material_commitment import SupplierMaterialCommitment  # noqa: E402
from app.models.task_collaboration import TaskActivityLog, TaskComment  # noqa: E402
from app.models.user import User  # noqa: E402

# Children → parents so FK constraints are satisfied. supplier_master is handled
# separately (last), after supplier-login users + supplier_emails.
ORDERED = [
    ("hi_agent_chat_messages", HiAgentChatMessage),
    ("task_activity_logs", TaskActivityLog),
    ("task_comments", TaskComment),
    ("status_change_log", StatusChangeLog),
    ("supplier_material_commitments", SupplierMaterialCommitment),
    ("communication_messages", CommunicationMessage),
    ("customer_mails", CustomerMail),
    ("communication_tasks", CommunicationTask),
    ("mail_history", MailHistory),
    ("followup_attempts", FollowupAttempt),
    ("notifications", Notification),
    ("ai_feedback", AIFeedback),
    ("asn_events", AsnEvent),
    ("asn_items", AsnItem),
    ("asns", Asn),
    ("procurement_records", ProcurementRecord),
]


def _count(db, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def main() -> None:
    ap = argparse.ArgumentParser(description="Purge sample POs + related data")
    ap.add_argument("--yes", action="store_true", help="execute the delete (otherwise dry-run)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        supplier_users = int(
            db.scalar(select(func.count()).select_from(User).where(User.supplier_id.is_not(None))) or 0
        )
        kept_users = int(
            db.scalar(select(func.count()).select_from(User).where(User.supplier_id.is_(None))) or 0
        )

        print("=== BEFORE ===")
        for label, model in ORDERED:
            print(f"  {label:34} {_count(db, model):>8}")
        print(f"  {'supplier_emails':34} {_count(db, SupplierEmail):>8}")
        print(f"  {'supplier_master':34} {_count(db, SupplierMaster):>8}")
        print(f"  {'users: supplier logins (DELETE)':34} {supplier_users:>8}")
        print(f"  {'users: staff+employee (KEEP)':34} {kept_users:>8}")

        if not args.yes:
            print("\nDRY RUN — pass --yes to execute.")
            return

        print("\nDeleting...")
        try:
            for _, model in ORDERED:
                db.execute(delete(model))
            # Supplier-specific mail-parse rules reference supplier_master — drop
            # them (keep global rules). Then supplier-login users BEFORE
            # supplier_master (users.supplier_id FK), then suppliers.
            db.execute(delete(MailParseRule).where(MailParseRule.supplier_id.is_not(None)))
            db.execute(delete(User).where(User.supplier_id.is_not(None)))
            db.execute(delete(SupplierEmail))
            db.execute(delete(SupplierMaster))
            db.commit()
        except Exception:
            db.rollback()
            print("ERROR — rolled back, nothing deleted.")
            raise

        print("\n=== AFTER ===")
        for label, model in ORDERED:
            print(f"  {label:34} {_count(db, model):>8}")
        print(f"  {'supplier_emails':34} {_count(db, SupplierEmail):>8}")
        print(f"  {'supplier_master':34} {_count(db, SupplierMaster):>8}")
        print(f"  {'users (total KEPT)':34} {_count(db, User):>8}")
        print("\nDone. Live CRM ingestion will repopulate POs + suppliers.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
