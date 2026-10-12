import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator

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
    
    # Environment mode: development, production, test
    APP_ENV: str = "development"

    # JWT Authentication settings (JWT_SECRET has no default; app refuses to start without it)
    JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "safestrata-auth"
    JWT_AUDIENCE: str = "safestrata-app"

    # OTP settings
    OTP_PEPPER: str = "safestrata-otp-server-pepper-secret-2026"
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60

    # SMTP Settings (Config only via .env)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "no-reply@safestrata.local"
    SMTP_STARTTLS: bool = True
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: float = 10.0

    # Knowledge Graph settings
    GRAPH_STORAGE_PATH: str = str(BASE_DIR / "data" / "knowledge_graph.json")
    ENABLE_GRAPH_ENRICHMENT: bool = True

    model_config = {
        "env_file": ".env",
        "extra": "allow"
    }

    @model_validator(mode="after")
    def validate_security_settings(self):
        if not self.JWT_SECRET:
            raise ValueError(
                "JWT_SECRET is not configured! The application refuses to start without an explicit JWT_SECRET. "
                "Please configure JWT_SECRET in your .env file or environment."
            )
        return self

settings = Settings()
