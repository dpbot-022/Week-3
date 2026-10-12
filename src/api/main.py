import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.logging import logger
from src.api.v1.health import router as health_router
from src.api.v1.documents import router as documents_router
from src.api.v1.search import router as search_router
from src.api.v1.rag import router as rag_router
from src.api.v1.guardrails import router as guardrails_router
from src.api.v1.graph import router as graph_router
from src.api.v1.evaluations import router as evals_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Enterprise Hybrid RAG & Guardrails application...")
    # Warm up local models in background
    from src.embeddings.provider import embedding_provider
    from src.retrieval.reranker import reranker
    try:
        embedding_provider.encode("system warm-up")
        logger.info("Local SentenceTransformer initialized.")
    except Exception as e:
        logger.warning(f"Embedding warm-up note: {e}")
    yield
    logger.info("Shutting down Enterprise Hybrid RAG application.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Production-grade Hybrid Search RAG pipeline with local Hugging Face models, PII guardrails, and automated evaluations.",
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
                "message": "An unexpected internal server error occurred.",
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
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(rag_router, prefix=settings.API_V1_STR)
app.include_router(guardrails_router, prefix=settings.API_V1_STR)
app.include_router(graph_router, prefix=settings.API_V1_STR)
app.include_router(evals_router, prefix=settings.API_V1_STR)

# Serve Web UI
@app.get("/", include_in_schema=False)
async def serve_ui():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Enterprise Hybrid RAG Pipeline API active. Visit /docs for OpenAPI documentation."}
