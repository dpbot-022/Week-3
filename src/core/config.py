import os
from pathlib import Path
from typing import List, Optional
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
    
    # Persistence & SQLite
    SQLITE_DB_PATH: str = str(BASE_DIR / "data" / "safestrata.db")
    DATABASE_URL: str = ""
    
    # Auth & RBAC
    APP_ENV: str = "development"
    JWT_SECRET: str = "safestrata-secure-internal-compliance-key-2026-jwt-token"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "safestrata-auth"
    JWT_AUDIENCE: str = "safestrata-app"
    OTP_PEPPER: str = "safestrata-otp-server-pepper-secret-2026"
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    AUDIT_TOKEN: str = "safestrata-audit-secret-token"
    ADMIN_EMAILS: List[str] = ["admin@safestrata.internal", "admin@bank.com", "admin@safestrata.local"]
    
    # Ollama & Local AI
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b-instruct"
    NLI_MODEL: str = "cross-encoder/nli-deberta-v3-small"
    PROMPT_INJECTION_MODEL: str = "ProtectAI/deberta-v3-base-prompt-injection-v2"
    NLI_SUPPORT_THRESHOLD: float = 0.5
    
    # Email / SMTP
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USER: str = ""
    SMTP_FROM: str = "SafeStrata Compliance Desk <no-reply@safestrata.internal>"
    SMTP_USE_TLS: bool = True
    SMTP_STARTTLS: bool = True
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: float = 10.0

    model_config = {
        "env_file": ".env",
        "extra": "allow"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"sqlite:///{self.SQLITE_DB_PATH}"

        calib_file = BASE_DIR / "data" / "calibration.json"
        if calib_file.exists():
            try:
                import json
                with open(calib_file, "r", encoding="utf-8") as f:
                    calib_data = json.load(f)
                if "optimal_relevance_threshold" in calib_data:
                    self.RELEVANCE_THRESHOLD = float(calib_data["optimal_relevance_threshold"])
                if "optimal_nli_support_threshold" in calib_data:
                    self.NLI_SUPPORT_THRESHOLD = float(calib_data["optimal_nli_support_threshold"])
            except Exception:
                pass

settings = Settings()
