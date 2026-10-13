from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import AuditLog, User
from src.auth.deps import require_permission
from src.core.rbac import PERM_READ_AUDIT

router = APIRouter(prefix="/audit", tags=["Audit"])

@router.get("/logs")
def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = None,
    user_email: Optional[str] = None,
    db: Session = Depends(get_db),
    auditor: User = Depends(require_permission(PERM_READ_AUDIT))
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.like(f"%{action}%"))
    if user_email:
        query = query.filter(AuditLog.user_email == user_email.lower().strip())

    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [l.to_dict() for l in logs]
    }
