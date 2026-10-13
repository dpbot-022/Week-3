import json
import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
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

@router.post("/stream")
async def execute_rag_stream(
    request: RAGRequest,
    current_user: User = Depends(require_permission(PERM_READ_RAG)),
    db: Session = Depends(get_db)
):
    """Streams grounded response via Server-Sent Events (SSE) with progressive status and token stream."""
    async def event_generator():
        # Event 1: Pipeline started
        yield f"event: status\ndata: {json.dumps({'stage': 'guardrails', 'message': 'Applying input PII and injection guardrails...'})}\n\n"
        await asyncio.sleep(0.01)

        # Execute full verified pipeline
        response = rag_pipeline.run(request, role=current_user.role, db=db)

        # Log to audit trail
        audit_service.log(
            user_email=current_user.email,
            role=current_user.role,
            action="rag:stream_executed",
            resource="rag_desk",
            details={
                "citations_count": len(response.citations),
                "faithfulness": response.faithfulness_score,
                "mode": response.generation_mode,
                "is_safe": response.guardrail_report.is_safe
            },
            db=db
        )

        yield f"event: status\ndata: {json.dumps({'stage': 'retrieval', 'message': f'Retrieved and verified {len(response.citations)} citations.'})}\n\n"
        await asyncio.sleep(0.01)

        # Stream answer tokens progressively
        answer_text = response.answer
        words = answer_text.split(" ")
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
            await asyncio.sleep(0.015)

        # Final completion event with full telemetry, citations, and trace
        yield f"event: complete\ndata: {response.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
