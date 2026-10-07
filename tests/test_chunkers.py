import pytest
from src.ingestion.chunkers import (
    CharacterChunker,
    RecursiveCharacterChunker,
    DocumentSpecificChunker,
    SemanticChunker,
    AgenticPropositionChunker,
    get_chunker
)
from src.schemas.models import ChunkingStrategy

SAMPLE_TEXT = """
# Hybrid Search Architecture
Hybrid search merges dense semantic vectors with sparse BM25 retrieval.
Dense vectors capture semantic concepts and relationships in embedding space.
Sparse retrieval matches exact keyword tokens and handles rare terminology.

## Reciprocal Rank Fusion
Reciprocal Rank Fusion (RRF) combines ranked lists using harmonic formula:
RRF score = sum(1 / (k + rank)).
Cross-encoder models perform joint attention over query and candidate passages.
"""

def test_character_chunker():
    chunker = CharacterChunker(chunk_size=100, chunk_overlap=10)
    chunks = chunker.chunk(SAMPLE_TEXT, "doc_1")
    assert len(chunks) > 1
    for c in chunks:
        assert c.strategy == ChunkingStrategy.CHARACTER
        assert len(c.content) <= 100

def test_recursive_character_chunker():
    chunker = RecursiveCharacterChunker(chunk_size=150, chunk_overlap=20)
    chunks = chunker.chunk(SAMPLE_TEXT, "doc_2")
    assert len(chunks) >= 1
    assert all(c.strategy == ChunkingStrategy.RECURSIVE for c in chunks)

def test_document_specific_chunker():
    chunker = DocumentSpecificChunker(chunk_size=200)
    chunks = chunker.chunk(SAMPLE_TEXT, "doc_3")
    assert len(chunks) >= 2
    assert any("Hybrid Search Architecture" in c.content for c in chunks)
    assert any("Reciprocal Rank Fusion" in c.content for c in chunks)

def test_semantic_chunker():
    chunker = SemanticChunker(breakpoint_percentile=80.0)
    chunks = chunker.chunk(SAMPLE_TEXT, "doc_4")
    assert len(chunks) >= 1
    assert all(c.strategy == ChunkingStrategy.SEMANTIC for c in chunks)

def test_agentic_proposition_chunker():
    chunker = AgenticPropositionChunker(max_propositions_per_chunk=3)
    chunks = chunker.chunk(SAMPLE_TEXT, "doc_5")
    assert len(chunks) >= 1
    assert all(c.strategy == ChunkingStrategy.AGENTIC for c in chunks)

def test_chunker_factory():
    c1 = get_chunker(ChunkingStrategy.CHARACTER)
    assert isinstance(c1, CharacterChunker)
    c2 = get_chunker(ChunkingStrategy.RECURSIVE)
    assert isinstance(c2, RecursiveCharacterChunker)
