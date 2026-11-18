from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import AuditAction
from app.core.dependencies import get_current_user, require_hr
from app.database.database import get_db
from app.models.internship_background import InternshipBackground
from app.models.user import User
from app.schemas.employee import BackgroundCreate, BackgroundOut, BackgroundUpdate
from app.services import audit_service

router = APIRouter(prefix="/internship-backgrounds", tags=["Internship Backgrounds"])


@router.get("", response_model=List[BackgroundOut])
def list_backgrounds(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(InternshipBackground)
    if active_only:
        query = query.filter(InternshipBackground.is_active.is_(True))
    return query.order_by(InternshipBackground.name).all()


@router.post("", response_model=BackgroundOut, status_code=status.HTTP_201_CREATED)
def create_background(
    payload: BackgroundCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    if (
        db.query(InternshipBackground)
        .filter(func.lower(InternshipBackground.name) == payload.name.lower())
        .first()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That background already exists."
        )

    background = InternshipBackground(**payload.model_dump())
    db.add(background)
    db.flush()
    audit_service.record(
        db, AuditAction.BACKGROUND_CREATED, user=current_user,
        entity_type="internship_background", entity_id=background.id,
        meta={"name": background.name},
    )
    db.commit()
    db.refresh(background)
    return background


@router.put("/{background_id}", response_model=BackgroundOut)
def update_background(
    background_id: int,
    payload: BackgroundUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    background = (
        db.query(InternshipBackground)
        .filter(InternshipBackground.id == background_id)
        .first()
    )
    if background is None:
        raise HTTPException(status_code=404, detail="Background not found.")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(background, field, value)
    db.flush()
    audit_service.record(
        db, AuditAction.BACKGROUND_UPDATED, user=current_user,
        entity_type="internship_background", entity_id=background.id,
        meta={"changes": {k: str(v) for k, v in changes.items()}},
    )
    db.commit()
    db.refresh(background)
    return background
