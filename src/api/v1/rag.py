from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src.schemas.models import RAGRequest, RAGResponse
from src.pipeline.rag_pipeline import rag_pipeline
from src.db.session import get_db
from src.db.models import User
from src.auth.deps import require_permission
from src.core.rbac import PERM_READ_RAG
from src.core.audit import audit_service

router = APIRouter(prefix="/rag", tags=["Grounded RAG Pipeline"])

@router.post("/query", response_model=RAGResponse)
async def execute_rag_query(
    request: RAGRequest,
    current_user: User = Depends(require_permission(PERM_READ_RAG)),
    db: Session = Depends(get_db)
):
    """Executes server-governed grounded RAG pipeline restricted to caller's verified role."""
    response = rag_pipeline.run(request, role=current_user.role, db=db)

    # Append-only audit log without logging raw query or PII
    audit_service.log(
        user_email=current_user.email,
        role=current_user.role,
        action="rag:query_executed",
        resource="rag_desk",
        details={
            "citations_count": len(response.citations),
            "faithfulness": response.faithfulness_score,
            "mode": response.generation_mode,
            "is_safe": response.guardrail_report.is_safe
        },
        db=db
    )

    return response
