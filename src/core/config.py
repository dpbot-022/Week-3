import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "SafeStrata: Layered Hybrid RAG & Guardrails Engine"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # Embedding & Reranker models
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    EMBEDDING_DIMENSION: int = 384
    
    # Vector store settings
    CHROMA_PERSIST_DIR: str = str(BASE_DIR / "data" / "chroma")
    DEFAULT_COLLECTION_NAME: str = "enterprise_knowledge"
    
    # Hybrid Search & RRF settings
    RRF_K: int = 60
    DEFAULT_TOP_K: int = 5
    DEFAULT_RETRIEVAL_LIMIT: int = 15
    HYBRID_ALPHA: float = 0.5  # Weight between dense (alpha) and sparse (1-alpha)
    
    # Guardrails settings
    GUARDRAILS_ENABLED: bool = True
    INJECTION_DETECTION_THRESHOLD: float = 0.65
    PII_REDACTION_ENABLED: bool = True
    CANARY_TOKEN_PREFIX: str = "SEC_CTX"
    AUDIT_TOKEN: str = "safestrata-audit-secret-token"
    
    # Generation & LLM settings
    LLM_PROVIDER: str = "local"  # "local", "gemini", "openai", "anthropic"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LOCAL_LLM_MODEL: str = "Qwen/Qwen2.5-0.5B-Instruct"
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.2
    RELEVANCE_THRESHOLD: float = 0.15  # Minimum score for passage grounding
    
    # Knowledge Graph settings
    GRAPH_STORAGE_PATH: str = str(BASE_DIR / "data" / "knowledge_graph.json")
    ENABLE_GRAPH_ENRICHMENT: bool = True
    
    model_config = {
        "env_file": ".env",
        "extra": "allow"
    }

settings = Settings()
