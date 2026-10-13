import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    role = Column(String(50), nullable=False, default="viewer")
    role_version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "role_version": self.role_version,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class OTPToken(Base):
    __tablename__ = "otp_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, index=True)
    otp_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)
    filename = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    allowed_roles_json = Column(Text, nullable=False, default='["viewer","analyst","compliance_manager","auditor"]')
    chunk_count = Column(Integer, default=0)
    effective_date = Column(String(64), nullable=True)
    pii_counts_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

    chunks = relationship("ChunkRecord", back_populates="document", cascade="all, delete-orphan")

    @property
    def allowed_roles(self) -> List[str]:
        try:
            return json.loads(self.allowed_roles_json)
        except Exception:
            return ["viewer", "analyst", "compliance_manager", "auditor"]

    @allowed_roles.setter
    def allowed_roles(self, roles: List[str]):
        self.allowed_roles_json = json.dumps(roles)

    @property
    def pii_counts(self) -> Dict[str, int]:
        try:
            return json.loads(self.pii_counts_json)
        except Exception:
            return {}

    @pii_counts.setter
    def pii_counts(self, counts: Dict[str, int]):
        self.pii_counts_json = json.dumps(counts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "allowed_roles": self.allowed_roles,
            "chunk_count": self.chunk_count,
            "effective_date": self.effective_date,
            "pii_counts": self.pii_counts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class ChunkRecord(Base):
    __tablename__ = "chunk_records"

    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, default=1)
    char_start = Column(Integer, default=0)
    char_end = Column(Integer, default=0)
    allowed_roles_json = Column(Text, nullable=False, default='["viewer","analyst","compliance_manager","auditor"]')
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")

    @property
    def allowed_roles(self) -> List[str]:
        try:
            return json.loads(self.allowed_roles_json)
        except Exception:
            return ["viewer", "analyst", "compliance_manager", "auditor"]

    @allowed_roles.setter
    def allowed_roles(self, roles: List[str]):
        self.allowed_roles_json = json.dumps(roles)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    resource = Column(String(255), nullable=True)
    details_json = Column(Text, default="{}")
    ip_address = Column(String(45), default="127.0.0.1")

    @property
    def details(self) -> Dict[str, Any]:
        try:
            return json.loads(self.details_json)
        except Exception:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_email": self.user_email,
            "role": self.role,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "ip_address": self.ip_address,
        }

class WrongAnswerReport(Base):
    __tablename__ = "wrong_answer_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_email = Column(String(255), nullable=False)
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    citations_json = Column(Text, default="[]")
    reason = Column(Text, nullable=False)
    status = Column(String(30), default="open")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_email": self.user_email,
            "query": self.query,
            "answer": self.answer,
            "citations": json.loads(self.citations_json) if self.citations_json else [],
            "reason": self.reason,
            "status": self.status,
        }

class SuggestedQuestion(Base):
    __tablename__ = "suggested_questions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
