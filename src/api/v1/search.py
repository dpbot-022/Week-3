import time
from fastapi import APIRouter, Depends
from src.schemas.models import SearchRequest, SearchResponse
from src.retrieval.hybrid_search import hybrid_search
from src.auth.deps import require_permission
from src.core.rbac import PERM_READ_RAG
from src.db.models import User

from src.retrieval.hyde import hyde_rewriter

router = APIRouter(prefix="/search", tags=["Hybrid Retrieval Engine"])

@router.post("", response_model=SearchResponse)
async def perform_search(
    request: SearchRequest,
    current_user: User = Depends(require_permission(PERM_READ_RAG))
):
    """Executes dense, sparse, or hybrid retrieval strictly filtered by user role."""
    start_time = time.time()
    transformed = hyde_rewriter.generate_hypothetical_document(request.query) if request.use_hyde else None
    results = hybrid_search.search(
        query=request.query,
        top_k=request.top_k,
        mode=request.mode,
        use_reranker=request.use_reranker,
        use_hyde=request.use_hyde,
        role=current_user.role,
        filter_metadata=request.filter_metadata
    )
    latency = round((time.time() - start_time) * 1000, 2)

    return SearchResponse(
        query=request.query,
        mode=request.mode,
        results=results,
        total_candidates=len(results),
        reranked=request.use_reranker,
        transformed_query=transformed,
        latency_ms=latency
    )
