from fastapi import APIRouter, Depends
from src.core.config import settings
from src.core.metrics import metrics
from src.vectorstore.chroma_store import vector_store
from src.auth.deps import require_permission
from src.core.rbac import PERM_READ_METRICS
from src.db.models import User

router = APIRouter(tags=["Health & Telemetry"])

@router.get("/health")
@router.get("/healthz")
async def health_check():
    """Health check endpoint providing vector store status, model info, and uptime."""
    doc_count = vector_store.count()
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "embedding_model": settings.EMBEDDING_MODEL,
        "reranker_model": settings.RERANKER_MODEL,
        "indexed_chunks": doc_count,
        "guardrails_active": settings.GUARDRAILS_ENABLED
    }

@router.get("/metrics")
async def get_metrics(
    admin_user: User = Depends(require_permission(PERM_READ_METRICS))
):
    """Telemetry metrics endpoint reporting query latencies and counters. Admin-only."""
    return metrics.get_summary()
