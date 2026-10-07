import pytest
from src.retrieval.bm25_search import bm25_engine
from src.retrieval.hyde import hyde_rewriter
from src.retrieval.deduplicator import deduplicator
from src.schemas.models import ScoredChunk

def test_bm25_indexing_and_search():
    docs = [
        {"id": "doc1", "content": "FastAPI is a modern async web framework for Python.", "metadata": {}},
        {"id": "doc2", "content": "Docker provides containerization and reproducible runtime environments.", "metadata": {}},
        {"id": "doc3", "content": "ChromaDB stores high dimensional dense vector embeddings.", "metadata": {}}
    ]
    bm25_engine.index_documents(docs)
    results = bm25_engine.search("FastAPI Python", top_k=2)
    assert len(results) > 0
    assert results[0].id == "doc1"
    assert results[0].sparse_score > 0.0

def test_hyde_query_expansion():
    query = "What is Reciprocal Rank Fusion?"
    hypo = hyde_rewriter.generate_hypothetical_document(query)
    assert len(hypo) > len(query)
    assert "Reciprocal Rank Fusion" in hypo

    variations = hyde_rewriter.expand_query(query)
    assert len(variations) >= 2

def test_canary_token_wrapping():
    from src.guardrails.injection_guard import injection_guard
    wrapped = injection_guard.wrap_canary_boundary("hello world")
    assert "USER_INPUT" in wrapped
    assert "hello world" in wrapped


def test_context_deduplicator():
    chunks = [
        ScoredChunk(id="c1", document_id="d1", content="Hybrid search merges dense semantic vectors with sparse BM25 retrieval.", final_score=0.9),
        ScoredChunk(id="c2", document_id="d1", content="Hybrid search merges dense semantic vectors with sparse BM25 retrieval exactly.", final_score=0.88),
        ScoredChunk(id="c3", document_id="d2", content="NetworkX creates entity graphs and traverses relationship edges.", final_score=0.7)
    ]
    deduped = deduplicator.deduplicate(chunks, max_chunks=3)
    # c2 is a near-duplicate of c1 and should be pruned
    assert len(deduped) == 2
    assert deduped[0].id == "c1"
    assert deduped[1].id == "c3"
