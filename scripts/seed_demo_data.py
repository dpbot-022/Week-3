#!/usr/bin/env python3
"""
SafeStrata - Demo Data Seeding Script
Reads the production knowledge corpus and populates ChromaDB, BM25, and NetworkX Knowledge Graph.
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import BASE_DIR, settings
from src.ingestion.parsers import DocumentParser
from src.ingestion.chunkers import get_chunker
from src.schemas.models import ChunkingStrategy
from src.embeddings.provider import embedding_provider
from src.vectorstore.chroma_store import vector_store
from src.retrieval.bm25_search import bm25_engine
from src.knowledge_graph.graph_store import knowledge_graph

def seed_database():
    sample_path = BASE_DIR / "data" / "sample" / "production_knowledge.md"
    if not sample_path.exists():
        print(f"Error: Sample file not found at {sample_path}")
        sys.exit(1)

    print("=" * 65)
    print("🚀 SafeStrata: Seeding Demo Knowledge Corpus")
    print("=" * 65)
    
    start_time = time.time()
    content = sample_path.read_text(encoding="utf-8")
    title = "Enterprise Architecture & Production RAG Standards"
    doc_id = "doc-safestrata-demo-001"

    print(f"📄 Loaded sample document: {sample_path.name} ({len(content)} characters)")
    
    # 1. Parsing & Chunking
    cleaned_content, _ = DocumentParser.parse_text(content, title)
    chunker = get_chunker(
        strategy=ChunkingStrategy.DOCUMENT_SPECIFIC,
        chunk_size=500,
        chunk_overlap=50,
        embedding_provider=embedding_provider
    )
    chunks = chunker.chunk(cleaned_content, doc_id)
    print(f"🧩 Produced {len(chunks)} structured chunks using {ChunkingStrategy.DOCUMENT_SPECIFIC.value}")

    # 2. Dense Embeddings
    print(f"🧠 Generating dense embeddings via '{settings.EMBEDDING_MODEL}'...")
    chunk_texts = [c.content for c in chunks]
    embeddings_np = embedding_provider.encode(chunk_texts)
    embeddings_list = [emb.tolist() for emb in embeddings_np]

    # 3. ChromaDB Vector Store
    print(f"💾 Storing vectors in persistent ChromaDB ({settings.CHROMA_PERSIST_DIR})...")
    vector_store.add_chunks(chunks=chunks, embeddings=embeddings_list)

    # 4. BM25 Sparse Index
    print("📚 Updating BM25 sparse index...")
    all_chunks = vector_store.get_all_chunks()
    bm25_engine.index_documents(all_chunks)

    # 5. Knowledge Graph Enrichment
    print("🕸️ Extracting entities and relations into NetworkX Knowledge Graph...")
    for chunk in chunks:
        knowledge_graph.add_entities_and_relations(chunk.content, doc_id)

    num_nodes = knowledge_graph.graph.number_of_nodes()
    num_edges = knowledge_graph.graph.number_of_edges()
    total_elapsed = round((time.time() - start_time), 2)

    print("\n" + "=" * 65)
    print("✅ SafeStrata Corpus Seeding Complete!")
    print(f"   • Total Chunks Indexed:     {len(all_chunks)}")
    print(f"   • BM25 Documents Indexed:   {len(bm25_engine.corpus_docs)}")
    print(f"   • Knowledge Graph Nodes:    {num_nodes}")
    print(f"   • Knowledge Graph Edges:    {num_edges}")
    print(f"   • Elapsed Time:             {total_elapsed}s")
    print("=" * 65)

if __name__ == "__main__":
    seed_database()
