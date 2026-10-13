from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import User
from src.auth.deps import require_permission
from src.core.rbac import PERM_MANAGE_USERS, ALL_ROLES, Role
from src.core.audit import audit_service

router = APIRouter(prefix="/admin", tags=["Admin"])

class RoleUpdateRequest(BaseModel):
    role: str

class StatusUpdateRequest(BaseModel):
    is_active: bool

@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_permission(PERM_MANAGE_USERS))
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [u.to_dict() for u in users]

@router.put("/users/{email}/role")
def update_user_role(
    email: str,
    payload: RoleUpdateRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_permission(PERM_MANAGE_USERS))
):
    clean_email = email.lower().strip()
    new_role = payload.role.strip()
    if new_role not in ALL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{new_role}'. Allowed roles: {ALL_ROLES}"
        )

    target_user = db.query(User).filter(User.email == clean_email).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # CRITICAL: Last-admin protection
    if target_user.role == Role.ADMIN.value and new_role != Role.ADMIN.value:
        active_admins = db.query(User).filter(User.role == Role.ADMIN.value, User.is_active == True).count()
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security policy violation: Cannot demote the last active administrator."
            )

    old_role = target_user.role
    target_user.role = new_role
    target_user.role_version += 1  # Increment version so role changes take effect immediately
    db.commit()
    db.refresh(target_user)

    audit_service.log(
        user_email=admin_user.email,
        role=admin_user.role,
        action="admin:role_change",
        resource=f"user:{clean_email}",
        details={"old_role": old_role, "new_role": new_role, "role_version": target_user.role_version}
    )

    return {
        "message": f"Updated role for {clean_email} from '{old_role}' to '{new_role}'.",
        "user": target_user.to_dict()
    }

@router.put("/users/{email}/status")
def update_user_status(
    email: str,
    payload: StatusUpdateRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_permission(PERM_MANAGE_USERS))
):
    clean_email = email.lower().strip()
    target_user = db.query(User).filter(User.email == clean_email).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # CRITICAL: Last-admin protection against disabling
    if target_user.role == Role.ADMIN.value and not payload.is_active:
        active_admins = db.query(User).filter(User.role == Role.ADMIN.value, User.is_active == True).count()
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security policy violation: Cannot disable the last active administrator."
            )

    target_user.is_active = payload.is_active
    db.commit()
    db.refresh(target_user)

    audit_service.log(
        user_email=admin_user.email,
        role=admin_user.role,
        action="admin:status_change",
        resource=f"user:{clean_email}",
        details={"is_active": target_user.is_active}
    )

    return {
        "message": f"Updated status for {clean_email} to {'active' if target_user.is_active else 'inactive'}.",
        "user": target_user.to_dict()
    }
