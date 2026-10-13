from typing import Optional
from fastapi import Depends
from src.vectorstore.chroma_store import vector_store, ChromaVectorStore
from src.retrieval.hybrid_search import hybrid_search, HybridSearchEngine
from src.pipeline.rag_pipeline import rag_pipeline, RAGPipeline
from src.knowledge_graph.graph_store import knowledge_graph, KnowledgeGraphEngine
from src.evaluation.benchmark import benchmark_runner, BenchmarkRunner
from src.auth.deps import get_current_user

def get_vector_store() -> ChromaVectorStore:
    return vector_store

def get_hybrid_search() -> HybridSearchEngine:
    return hybrid_search

def get_rag_pipeline() -> RAGPipeline:
    return rag_pipeline

def get_knowledge_graph() -> KnowledgeGraphEngine:
    return knowledge_graph

def get_benchmark_runner() -> BenchmarkRunner:
    return benchmark_runner
