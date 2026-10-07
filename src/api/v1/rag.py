from fastapi import APIRouter, Depends
from src.schemas.models import RAGRequest, RAGResponse
from src.api.deps import get_rag_pipeline

router = APIRouter(prefix="/rag", tags=["Retrieval-Augmented Generation"])

@router.post("/query", response_model=RAGResponse)
async def query_rag_pipeline(
    request: RAGRequest,
    rag_pipeline=Depends(get_rag_pipeline)
):
    """Executes the end-to-end RAG pipeline with guardrails, hybrid search, graph traversal, and generation."""
    return rag_pipeline.run(request)
