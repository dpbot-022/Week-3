import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.logging import logger
from src.db.session import init_db, SessionLocal
from src.retrieval.bm25_search import bm25_manager
from src.auth.deps import require_permission
from src.core.rbac import PERM_READ_METRICS
from src.core.metrics import metrics
from src.db.models import User

from src.api.v1.health import router as health_router
from src.api.v1.auth import router as auth_router
from src.api.v1.admin import router as admin_router
from src.api.v1.audit import router as audit_router
from src.api.v1.documents import router as documents_router
from src.api.v1.search import router as search_router
from src.api.v1.rag import router as rag_router
from src.api.v1.guardrails import router as guardrails_router
from src.api.v1.graph import router as graph_router
from src.api.v1.evaluations import router as evals_router
from src.api.v1.quality import router as quality_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing SafeStrata Compliance Desk platform...")
    # 1. Initialize SQLite schema
    init_db()
    # 2. Rebuild per-role BM25 indices from SQLite
    try:
        with SessionLocal() as db:
            bm25_manager.rebuild_from_db(db)
        logger.info("Per-role BM25 indices initialized.")
    except Exception as e:
        logger.warning(f"BM25 index initialization warning: {e}")

    # 3. Warm up local embeddings
    from src.embeddings.provider import embedding_provider
    try:
        embedding_provider.encode("SafeStrata system warm-up")
        logger.info("SentenceTransformer embeddings warm.")
    except Exception as e:
        logger.warning(f"Embedding warm-up warning: {e}")

    yield
    logger.info("SafeStrata shutdown.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="SafeStrata: Production-Grade Layered Hybrid Search RAG Pipeline with RBAC, Email-OTP, and Automated Evaluations.",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID & Latency Middleware
@app.middleware("http")
async def add_process_time_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = round((time.time() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-MS"] = str(process_time)
        return response
    except Exception as exc:
        process_time = round((time.time() - start_time) * 1000, 2)
        logger.error(f"Unhandled Exception for Request {request_id}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": str(exc),
                "request_id": request_id,
                "latency_ms": process_time
            },
            headers={"X-Request-ID": request_id, "X-Process-Time-MS": str(process_time)}
        )

# Mount Static Files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount API Routers
app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(audit_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(rag_router, prefix=settings.API_V1_STR)
app.include_router(guardrails_router, prefix=settings.API_V1_STR)
app.include_router(graph_router, prefix=settings.API_V1_STR)
app.include_router(evals_router, prefix=settings.API_V1_STR)
app.include_router(quality_router, prefix=settings.API_V1_STR)

# Admin-only /metrics route at root level
@app.get("/metrics", tags=["Telemetry"], include_in_schema=False)
async def root_metrics(admin_user: User = Depends(require_permission(PERM_READ_METRICS))):
    return metrics.get_summary()

# Root health check
@app.get("/healthz", include_in_schema=False)
async def root_healthz():
    return {"status": "healthy"}

# Serve Web UI
@app.get("/", include_in_schema=False)
async def serve_ui():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "SafeStrata API active. Visit /docs for OpenAPI documentation."}
