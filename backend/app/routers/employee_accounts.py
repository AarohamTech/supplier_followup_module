"""Admin management of internal employee portal logins. Every route requires admin.

Employee logins are `User` rows with `role="employee"` and an `emp_code`. They are
provisioned from the Hariom employee sheet (username = login id), get a random
temp password (handed out via an Excel — no employee email), and force a change
on first login. Admins can add/remove/reset/activate here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import require_admin
from ..database import get_db
from ..models.user import User
from ..schemas.user import UserOut
from ..services import employee_account_service as svc
from ..services.user_service import EmailTakenError, UsernameTakenError

router = APIRouter(
    prefix="/api/employee-accounts",
    tags=["employee-accounts"],
    dependencies=[Depends(require_admin)],
)


class EmployeeCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    full_name: str | None = Field(default=None, max_length=255)
    emp_code: str | None = Field(default=None, max_length=32)


class CredItem(BaseModel):
    full_name: str | None = None
    username: str | None = None
    temp_password: str | None = None


def _load_employee_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.emp_code is None:
        raise HTTPException(status_code=404, detail="Employee login not found")
    return user


@router.get("", response_model=list[UserOut])
def list_logins(db: Session = Depends(get_db)) -> list[User]:
    return svc.list_employee_logins(db)


@router.post("/import-sheet")
async def import_sheet(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> dict:
    content = await file.read()
    try:
        rows = svc.parse_employee_sheet(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read sheet: {exc}")
    if not rows:
        raise HTTPException(status_code=400, detail="No rows found in the sheet")
    result = svc.provision_from_rows(db, rows)
    return {"ok": True, **result}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_one(payload: EmployeeCreate, db: Session = Depends(get_db)) -> dict:
    try:
        result = svc.create_employee(
            db,
            username=payload.username,
            full_name=payload.full_name,
            emp_code=payload.emp_code,
        )
    except (EmailTakenError, UsernameTakenError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, **result}


@router.post("/credentials.xlsx")
def download_credentials(items: list[CredItem], db: Session = Depends(get_db)) -> Response:
    data = svc.credentials_workbook([it.model_dump() for it in items])
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=employee_credentials.xlsx"},
    )


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = _load_employee_user(db, user_id)
    return {"ok": True, **svc.reset_employee_password(db, user)}


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate(user_id: int, db: Session = Depends(get_db)) -> User:
    user = _load_employee_user(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/activate", response_model=UserOut)
def activate(user_id: int, db: Session = Depends(get_db)) -> User:
    user = _load_employee_user(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_employee(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = _load_employee_user(db, user_id)
    db.delete(user)
    db.commit()
    return {"ok": True, "deleted": user_id}
