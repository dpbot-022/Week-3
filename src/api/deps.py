from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from src.vectorstore.chroma_store import vector_store, ChromaVectorStore
from src.retrieval.hybrid_search import hybrid_search, HybridSearchEngine
from src.pipeline.rag_pipeline import rag_pipeline, RAGPipeline
from src.knowledge_graph.graph_store import knowledge_graph, KnowledgeGraphEngine
from src.evaluation.benchmark import benchmark_runner, BenchmarkRunner
from src.auth.jwt_handler import decode_access_token
from src.auth.store import auth_store, UserRecord

security_bearer = HTTPBearer(auto_error=False)

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

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)) -> UserRecord:
    """Dependency that strictly validates Bearer access tokens and extracts authenticated user context."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Missing Bearer access token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: Missing subject identifier.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = auth_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or session revoked.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user
