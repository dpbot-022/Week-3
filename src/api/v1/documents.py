import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from src.schemas.models import (
    IngestDocumentRequest, IngestResponse, ChunkPreviewRequest,
    ChunkingStrategy, Chunk, ChunkPreviewResponse, ResetResponse
)
from src.ingestion.chunkers import get_chunker
from src.ingestion.parsers import DocumentParser
from src.embeddings.provider import embedding_provider
from src.api.deps import get_vector_store, get_knowledge_graph
from src.retrieval.bm25_search import bm25_engine
from src.core.metrics import metrics

router = APIRouter(prefix="/documents", tags=["Document Ingestion & Chunking"])

@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    request: IngestDocumentRequest,
    vector_store=Depends(get_vector_store),
    knowledge_graph=Depends(get_knowledge_graph)
):
    """Ingests a document through parsing, multi-level chunking, embedding, vector storage, and KG enrichment."""
    start_time = time.time()
    
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Document content cannot be empty.")

    doc_id = str(uuid.uuid4())
    cleaned_content, parse_meta = DocumentParser.parse_text(request.content, request.title)

    # 1. Chunking via selected strategy
    chunker = get_chunker(
        strategy=request.strategy,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        embedding_provider=embedding_provider
    )
    chunks = chunker.chunk(cleaned_content, doc_id)

    if not chunks:
        raise HTTPException(status_code=400, detail="Failed to produce chunks from the document content.")

    # 2. Embedding via SentenceTransformers
    chunk_texts = [c.content for c in chunks]
    embeddings_np = embedding_provider.encode(chunk_texts)
    embeddings_list = [emb.tolist() for emb in embeddings_np]

    # 3. Vector Storage in ChromaDB
    vector_store.add_chunks(chunks=chunks, embeddings=embeddings_list)

    # 4. Synchronize BM25 sparse index with all active corpus
    all_chunks = vector_store.get_all_chunks()
    bm25_engine.index_documents(all_chunks)

    # 5. Extract entities and enrich Knowledge Graph
    for chunk in chunks:
        knowledge_graph.add_entities_and_relations(chunk.content, doc_id)

    latency = round((time.time() - start_time) * 1000, 2)
    metrics.increment("documents_ingested")
    metrics.increment("chunks_indexed", len(chunks))

    return IngestResponse(
        document_id=doc_id,
        title=request.title,
        strategy=request.strategy,
        chunk_count=len(chunks),
        chunks=chunks,
        entities_extracted=knowledge_graph.graph.number_of_nodes(),
        latency_ms=latency
    )

@router.post("/preview-chunking", response_model=ChunkPreviewResponse)
async def preview_chunking(request: ChunkPreviewRequest):
    """Previews chunking behavior for interactive visualization across strategies."""
    start_time = time.time()
    temp_doc_id = "preview_doc"
    chunker = get_chunker(
        strategy=request.strategy,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        embedding_provider=embedding_provider
    )
    chunks = chunker.chunk(request.text, temp_doc_id)
    latency = round((time.time() - start_time) * 1000, 2)

    return ChunkPreviewResponse(
        strategy=request.strategy,
        chunk_count=len(chunks),
        chunks=chunks,
        latency_ms=latency
    )

@router.post("/reset", response_model=ResetResponse)
async def reset_documents(
    vector_store=Depends(get_vector_store),
    knowledge_graph=Depends(get_knowledge_graph)
):
    """Resets ChromaDB collection, BM25 index, and Knowledge Graph."""
    vector_store.reset_collection()
    bm25_engine.index_documents([])
    knowledge_graph.graph.clear()
    knowledge_graph.save()
    return ResetResponse(status="success", message="All vector store and knowledge graph data reset.")
