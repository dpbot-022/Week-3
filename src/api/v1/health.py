from fastapi import APIRouter
from src.core.config import settings
from src.core.metrics import metrics
from src.vectorstore.chroma_store import vector_store
from src.schemas.models import HealthResponse, MetricsResponse

router = APIRouter(tags=["Health & Telemetry"])

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint providing vector store status, model info, and uptime."""
    doc_count = vector_store.count()
    return HealthResponse(
        status="healthy",
        project=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        embedding_model=settings.EMBEDDING_MODEL,
        reranker_model=settings.RERANKER_MODEL,
        indexed_chunks=doc_count,
        guardrails_active=settings.GUARDRAILS_ENABLED
    )

@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Telemetry metrics endpoint reporting query latencies and counters."""
    data = metrics.get_summary()
    return MetricsResponse(
        counters=data.get("counters", {}),
        latencies=data.get("latencies", {}),
        uptime_seconds=data.get("uptime_seconds", 0.0)
    )
