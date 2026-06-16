"""Seed defaults: mail templates, supplier emails, and sample procurement records."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.config import settings
from .database import Base, SessionLocal, engine, ensure_schema
from .models.mail_history import MailHistory  # noqa: F401
from .models.mail_template import MailTemplate  # noqa: F401
from .models.procurement import ProcurementRecord  # noqa: F401
from .models.supplier import SupplierMaster  # noqa: F401
from .models.supplier_email import SupplierEmail  # noqa: F401
from .models.user import User  # noqa: F401
from .schemas.procurement import ProcurementCreate
from .services import user_service
from .services.procurement_sync_service import sync_records


TEMPLATES = [
    dict(
        template_name="GREEN_PO_RELEASE", signal="GREEN", day_no=0,
        subject_template="PO Acknowledgement | PO No. {{supplier_po_no}} | {{material_name}} | {{supplier_name}}",
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "We have released PO No. {{supplier_po_no}} (CRM {{crm_no}}) for "
            "{{material_name}} - Qty {{qty}} {{uom}}.\n"
            "Kindly acknowledge the order and confirm shipment plan by {{shipment_date}}.\n\n"
            "Regards,\nProcurement"
        ),
    ),
    dict(
        template_name="YELLOW_REMINDER", signal="YELLOW", day_no=0,
        subject_template="Reminder | PO No. {{supplier_po_no}} | {{material_name}} | {{supplier_name}}",
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "This is a polite reminder for PO No. {{supplier_po_no}} / {{material_name}} "
            "(Qty {{qty}}). Required ship date: {{shipment_date}}. Please confirm dispatch plan.\n\n"
            "Regards,\nProcurement"
        ),
    ),
    dict(
        template_name="RED_DAY1", signal="RED", day_no=1,
        subject_template="Urgent Follow-up | PO No. {{supplier_po_no}} | {{material_name}} | {{supplier_name}}",
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "PO No. {{supplier_po_no}} for {{material_name}} (Qty {{qty}}) is now overdue. "
            "Please share immediate dispatch confirmation.\n\n"
            "Regards,\nProcurement"
        ),
    ),
    dict(
        template_name="RED_DAY2", signal="RED", day_no=2,
        subject_template="Strong Follow-up | PO No. {{supplier_po_no}} | {{material_name}} | {{supplier_name}}",
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "We have not received any response on PO No. {{supplier_po_no}} / {{material_name}}. "
            "This is the 2nd urgent reminder. Kindly revert today with dispatch plan, "
            "failing which the matter will be escalated.\n\n"
            "Regards,\nProcurement"
        ),
    ),
    dict(
        template_name="BLACK_ESCALATION", signal="BLACK", day_no=0,
        subject_template="Critical Escalation | PO No. {{supplier_po_no}} | {{material_name}} | {{supplier_name}}",
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "PO No. {{supplier_po_no}} / {{material_name}} is now flagged BLACK "
            "(critical shortage). [AI follow-up content will be inserted here for serious escalation.]\n\n"
            "Regards,\nProcurement"
        ),
    ),
    dict(
        template_name="PO_FOLLOWUP_GROUP", signal="GREEN", day_no=0,
        subject_template=(
            "PO Follow-up | PO No. {{supplier_po_no}} | {{material_count}} material(s) | {{supplier_name}}"
        ),
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "This is a follow-up for PO No. {{supplier_po_no}} covering {{material_count}} material(s). "
            "Overall risk signal: {{overall_signal}}. Earliest required dispatch: {{earliest_due_date}}.\n\n"
            "Material-wise summary:\n"
            "{{materials_table_text}}\n\n"
            "{{reply_instructions}}\n\n"
            "Regards,\nProcurement"
        ),
    ),
    dict(
        template_name="PO_FOLLOWUP_RED", signal="RED", day_no=0,
        subject_template=(
            "Urgent PO Follow-up | PO No. {{supplier_po_no}} | {{material_count}} material(s) | {{supplier_name}}"
        ),
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "PO No. {{supplier_po_no}} ({{material_count}} material(s)) is overdue or at high risk "
            "(overall signal: {{overall_signal}}, earliest due: {{earliest_due_date}}).\n\n"
            "Please share dispatch confirmation for each material:\n"
            "{{materials_table_text}}\n\n"
            "{{reply_instructions}}\n\n"
            "Regards,\nProcurement"
        ),
    ),
    dict(
        template_name="PO_FOLLOWUP_BLACK", signal="BLACK", day_no=0,
        subject_template=(
            "Critical PO Escalation | PO No. {{supplier_po_no}} | {{material_count}} material(s) | {{supplier_name}}"
        ),
        body_template=(
            "Dear {{supplier_name}},\n\n"
            "PO No. {{supplier_po_no}} is in BLACK (critical) state across {{material_count}} material(s).\n\n"
            "Material-wise dispatch status required immediately:\n"
            "{{materials_table_text}}\n\n"
            "{{reply_instructions}}\n\n"
            "Regards,\nProcurement"
        ),
    ),
]


SUPPLIER_EMAILS = [
    dict(supplier_name="TECHNOMECH ENGINEERING PRIVATE LIMITED",
         to_emails=["sales@technomech.example.com"],
         cc_emails=["purchase@example.com"],
         bcc_emails=[],
         escalation_emails=["md@example.com"]),
    dict(supplier_name="M/S SUPERB TOOLS",
         to_emails=["orders@superbtools.example.com"],
         cc_emails=["purchase@example.com"],
         bcc_emails=[],
         escalation_emails=["md@example.com"]),
]


SAMPLE_PROCUREMENT: list[dict] = [
    dict(
        crm_no="2526-012467",
        material_name="INDEXABLE GUN DRILL DIA 26.2 X OAL 1750 (QSK 60)",
        uom="NOS", lead_time=60, shipment_date="28-05-2026 16:25",
        signal="RED", stock=0, qty=4, po_status="APPROVED", adv_status="PENDING",
        supplier_po_no="2526-011274", supplier_date="31-03-2026",
        supplier_name="TECHNOMECH ENGINEERING PRIVATE LIMITED", quantity=4, rate=35226,
    ),
    dict(
        crm_no="2526-013112",
        material_name="CARBIDE END MILL DIA 12 X 75 (4 FLUTE)",
        uom="NOS", lead_time=45, shipment_date="20-04-2026 10:00",
        signal="BLACK", stock=0, qty=20, po_status="APPROVED", adv_status="PENDING",
        supplier_po_no="SBT-2526-0091", supplier_date="03-04-2026",
        supplier_name="M/S SUPERB TOOLS", quantity=20, rate=1875,
    ),
    dict(
        crm_no="2526-013150",
        material_name="HSS DRILL BIT DIA 8.5 (PARALLEL SHANK)",
        uom="NOS", lead_time=30, shipment_date="25-04-2026 09:30",
        signal="BLACK", stock=2, qty=200, po_status="APPROVED", adv_status="PENDING",
        supplier_po_no="SBT-2526-0102", supplier_date="06-04-2026",
        supplier_name="M/S SUPERB TOOLS", quantity=200, rate=128,
    ),
    dict(
        crm_no="2526-014001",
        material_name="REAMER DIA 10 X 100 (HSS-CO)",
        uom="NOS", lead_time=20, shipment_date="20-05-2026 12:00",
        signal="GREEN", stock=10, qty=50, po_status="APPROVED", adv_status="PENDING",
        supplier_po_no="TM-2526-0210", supplier_date="22-04-2026",
        supplier_name="TECHNOMECH ENGINEERING PRIVATE LIMITED", quantity=50, rate=540,
    ),
]


def init_schema() -> None:
    ensure_schema()
    Base.metadata.create_all(bind=engine)


def seed_templates(db: Session) -> int:
    added = 0
    for template in TEMPLATES:
        row = db.scalar(select(MailTemplate).where(MailTemplate.template_name == template["template_name"]))
        if row:
            for key, value in template.items():
                setattr(row, key, value)
        else:
            db.add(MailTemplate(**template))
            added += 1
    db.commit()
    return added


def seed_supplier_emails(db: Session) -> int:
    added = 0
    for supplier in SUPPLIER_EMAILS:
        master = db.scalar(
            select(SupplierMaster).where(SupplierMaster.supplier_name == supplier["supplier_name"])
        )
        if not master:
            continue
        existing = db.scalar(
            select(SupplierEmail).where(
                SupplierEmail.supplier_id == master.id,
                SupplierEmail.is_active.is_(True),
            )
        )
        data = {**supplier, "supplier_id": master.id, "is_active": True}
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
        else:
            db.add(SupplierEmail(**data))
            added += 1
    db.commit()
    return added


def seed_procurement(db: Session) -> dict:
    payloads = [ProcurementCreate(**row) for row in SAMPLE_PROCUREMENT]
    result = sync_records(db, payloads)
    return result.model_dump()


def seed_admin(db: Session) -> bool:
    """Bootstrap the first admin user from env (only when no users exist)."""
    return user_service.ensure_seed_admin(
        db,
        email=settings.SEED_ADMIN_EMAIL,
        password=settings.SEED_ADMIN_PASSWORD,
        full_name=settings.SEED_ADMIN_NAME,
    )


def run() -> dict:
    init_schema()
    db = SessionLocal()
    try:
        result = {
            "admin_seeded": seed_admin(db),
            "templates_added": seed_templates(db),
            "supplier_emails_added": seed_supplier_emails(db),
        }
        # Demo procurement rows are only seeded in DEBUG/dev — never auto-injected
        # into a production database.
        if settings.DEBUG:
            result["procurement_sync"] = seed_procurement(db)
        else:
            result["procurement_sync"] = "skipped (DEBUG off)"
        return result
    finally:
        db.close()


if __name__ == "__main__":
    print(run())
