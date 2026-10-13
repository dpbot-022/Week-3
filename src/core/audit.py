import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from src.db.models import AuditLog
from src.db.session import SessionLocal

class AuditService:
    """Append-only audit logging service. Enforces PII/raw-query sanitization."""

    @staticmethod
    def log(
        user_email: str,
        role: str,
        action: str,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: str = "127.0.0.1",
        db: Optional[Session] = None
    ) -> AuditLog:
        # Sanitize details to ensure NO raw queries, secrets, or OTPs are logged
        clean_details = {}
        if details:
            for k, v in details.items():
                if any(sensitive in k.lower() for sensitive in ["otp", "token", "password", "secret", "raw_query", "raw_pii"]):
                    clean_details[k] = "[REDACTED]"
                else:
                    clean_details[k] = v

        log_entry = AuditLog(
            user_email=user_email,
            role=role,
            action=action,
            resource=resource,
            details_json=json.dumps(clean_details),
            ip_address=ip_address,
            timestamp=datetime.utcnow()
        )

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            return log_entry
        finally:
            if should_close:
                db.close()

audit_service = AuditService()
