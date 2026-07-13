from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User
from app.core.deps import get_current_user, require_roles
from app.schemas.users import (
    UserMeResponse, UserPreferencesUpdate, AdminUserListResponse,
    BlockToggleResponse, RoleUpdateRequest, RoleUpdateResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/preferences", response_model=UserMeResponse)
def update_preferences(payload: UserPreferencesUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field in ("language", "fcm_token", "notif_push", "notif_sms", "notif_voice"):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/admin", response_model=AdminUserListResponse, dependencies=[Depends(require_roles("SuperAdmin"))])
def list_users(
    region: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if region:
        q = q.filter(User.region == region)
    if status_filter:
        q = q.filter(User.status == status_filter)
    total = q.count()
    items = q.order_by(User.last_active.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "items": items}


@router.put("/block/{user_id}", response_model=BlockToggleResponse, dependencies=[Depends(require_roles("SuperAdmin"))])
def toggle_block(user_id: str, db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    target.status = "Blocked" if target.status == "Active" else "Active"
    db.commit()
    return {"id": target.id, "status": target.status}


@router.put("/role/{user_id}", response_model=RoleUpdateResponse, dependencies=[Depends(require_roles("SuperAdmin"))])
def update_role(user_id: str, payload: RoleUpdateRequest, db: Session = Depends(get_db)):
    if payload.role not in ("SuperAdmin", "Moderator", "Viewer"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    target.role = payload.role
    db.commit()
    return {"id": target.id, "role": target.role}


@router.delete("/me")
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GDPR / African data-protection-law compliant self-deletion. Per the
    blueprint's Security & Compliance section, associated feedback rows are
    anonymized (user_id set NULL) rather than deleted, since they contribute
    to the RLHF training signal and aggregate risk stats."""
    db.query(User).filter(User.id == user.id).delete()
    db.commit()
    return {"message": "Account deleted"}
