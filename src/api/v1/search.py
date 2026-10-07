import time
from fastapi import APIRouter, Depends
from src.schemas.models import SearchRequest, SearchResponse
from src.api.deps import get_hybrid_search
from src.retrieval.hyde import hyde_rewriter

router = APIRouter(prefix="/search", tags=["Hybrid Search & Reranking"])

@router.post("", response_model=SearchResponse)
async def perform_search(
    request: SearchRequest,
    hybrid_search=Depends(get_hybrid_search)
):
    """Executes dense, sparse, or hybrid search with optional HyDE and Cross-Encoder reranking."""
    start_time = time.time()
    
    transformed_query = None
    if request.use_hyde:
        transformed_query = hyde_rewriter.generate_hypothetical_document(request.query)

    results = hybrid_search.search(
        query=request.query,
        top_k=request.top_k,
        mode=request.mode,
        use_reranker=request.use_reranker,
        use_hyde=request.use_hyde,
        filter_metadata=request.filter_metadata
    )

    latency = round((time.time() - start_time) * 1000, 2)

    return SearchResponse(
        query=request.query,
        transformed_query=transformed_query,
        mode=request.mode,
        results=results,
        total_candidates=len(results),
        reranked=request.use_reranker,
        latency_ms=latency
    )
