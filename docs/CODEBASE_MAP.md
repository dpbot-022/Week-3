# SafeStrata Codebase Map (Phase 0)

## 1. Directory Tree

```
safestrata/
├── Dockerfile
├── LICENSE
├── Makefile
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CODEBASE_MAP.md
│   ├── EVALUATION_REPORT.md
│   └── USER_GUIDE.md
├── reports/
│   ├── eval_20261012_035532_f82526d.json
│   ├── eval_20261012_035920_f82526d.json
│   └── latest_eval.json
├── scripts/
│   ├── benchmark_latency.py
│   ├── generate_gold_dataset.py
│   ├── run_evals.py
│   └── seed_demo_data.py
├── src/
│   ├── api/
│   │   ├── deps.py
│   │   ├── main.py
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── documents.py
│   │       ├── evaluations.py
│   │       ├── graph.py
│   │       ├── guardrails.py
│   │       ├── health.py
│   │       ├── rag.py
│   │       └── search.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── email_service.py
│   │   ├── jwt_handler.py
│   │   └── store.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── metrics.py
│   ├── embeddings/
│   │   └── provider.py
│   ├── evaluation/
│   │   ├── benchmark.py
│   │   └── rag_evaluator.py
│   ├── generation/
│   │   └── generator.py
│   ├── guardrails/
│   │   ├── injection_guard.py
│   │   ├── output_guard.py
│   │   └── pii_guard.py
│   ├── ingestion/
│   │   ├── chunkers.py
│   │   └── parsers.py
│   ├── knowledge_graph/
│   │   └── graph_store.py
│   ├── pipeline/
│   │   └── rag_pipeline.py
│   ├── retrieval/
│   │   ├── bm25_search.py
│   │   ├── deduplicator.py
│   │   ├── hybrid_search.py
│   │   ├── hyde.py
│   │   └── reranker.py
│   ├── schemas/
│   │   ├── auth_models.py
│   │   └── models.py
│   ├── static/
│   │   ├── app.js
│   │   ├── index.html
│   │   └── styles.css
│   └── vectorstore/
│       └── chroma_store.py
└── tests/
    ├── conftest.py
    ├── test_api.py
    ├── test_auth.py
    ├── test_chunkers.py
    ├── test_generator_providers.py
    ├── test_guardrails.py
    ├── test_guardrails_security_p0.py
    ├── test_knowledge_graph.py
    └── test_retrieval.py
```

---

## 2. Module Inventory & Decisions

| Module | Purpose (One Line) | Public Functions / Classes | Decision | Rationale |
|---|---|---|---|---|
| `src/api/deps.py` | FastAPI dependency injection providers for singletons and JWT user context. | `get_vector_store`, `get_hybrid_search`, `get_rag_pipeline`, `get_knowledge_graph`, `get_benchmark_runner`, `get_current_user` | **REFACTOR** | Prune deprecated graph and benchmark dependencies while maintaining tested auth bearer validation. |
| `src/api/main.py` | Application entrypoint, lifespan startup warm-up, latency middleware, and route mounting. | `app`, `lifespan`, `add_process_time_and_request_id`, `root_healthz`, `serve_ui` | **KEEP** | Core server configuration and middleware are stable, functioning, and tested. |
| `src/api/v1/auth.py` | Passwordless email OTP lifecycle, JWT token issuance, refresh rotation, and profile endpoints. | `router`, `request_otp`, `verify_otp`, `refresh_session`, `logout`, `get_current_user_profile` | **KEEP** | Meets all security requirements; tested with zero PII/OTP leakage and full enumeration defense. |
| `src/api/v1/documents.py` | Document ingestion, chunking preview, and collection reset endpoints. | `router`, `ingest_document`, `preview_chunking`, `reset_database` | **REFACTOR** | Synchronize dense Chroma index and in-memory BM25 index on reset and ingestion. |
| `src/api/v1/evaluations.py` | Trigger endpoint for benchmark evaluation suite. | `router`, `run_benchmark` | **REPLACE** | Evaluation harness is slated for complete overhaul in future phases. |
| `src/api/v1/graph.py` | Knowledge graph structure and stats inspection endpoint. | `router`, `get_graph` | **REPLACE** | Slated for removal/replacement alongside knowledge graph leftovers. |
| `src/api/v1/guardrails.py` | Public text sanitization inspection and authenticated pattern rule audit endpoints. | `router`, `check_guardrails`, `audit_guardrails` | **KEEP** | Enforces strict P0 sanitization and token-gated internal pattern auditing. |
| `src/api/v1/health.py` | Liveness health check and metrics dump endpoints. | `router`, `health_check`, `get_metrics` | **KEEP** | Standard, reliable system health probe. |
| `src/api/v1/rag.py` | End-to-end question answering pipeline execution endpoint. | `router`, `query_rag_pipeline` | **KEEP** | Simple, authenticated route cleanly delegating to pipeline engine. |
| `src/api/v1/search.py` | Hybrid search retrieval endpoint without generation. | `router`, `search_knowledge_base` | **KEEP** | Provides standalone dense + sparse retrieval with reranking. |
| `src/auth/__init__.py` | Auth package initialization marker. | None | **KEEP** | Standard package namespace marker. |
| `src/auth/email_service.py` | Async SMTP delivery via `aiosmtplib` with Jinja2 multipart templates and strict TLS enforcement. | `EmailService`, `email_service`, `SMTPConfigurationError`, `SMTPDeliveryError` | **KEEP** | Well-tested genuine email dispatch with production TLS verification. |
| `src/auth/jwt_handler.py` | Pinned HS256 access token issuance/verification and random refresh token generation. | `create_access_token`, `decode_access_token`, `create_refresh_token` | **KEEP** | Strict claim verification (`sub`, `exp`, `iss`, `aud`) pinned to HS256. |
| `src/auth/store.py` | In-memory store for users, peppered OTP hashes, rate limits, and refresh token families. | `AuthStore`, `auth_store`, `UserRecord`, `OTPRecord`, `RefreshTokenRecord` | **REPLACE** | In-memory store will be replaced by durable database persistence in a future phase. |
| `src/core/config.py` | Application settings loaded from `.env` using Pydantic Settings with startup validation. | `Settings`, `settings` | **KEEP** | Strict validation ensures application refuses startup without `JWT_SECRET`. |
| `src/core/logging.py` | Structured JSON log formatter with custom PII scrubbing filter. | `PIIRedactingFilter`, `setup_logging`, `logger` | **KEEP** | Tested P0 security component preventing raw PII strings from leaking into logs. |
| `src/core/metrics.py` | In-memory latency tracker and operational event counter. | `MetricsTracker`, `metrics` | **KEEP** | Lightweight, thread-safe metrics collection. |
| `src/embeddings/provider.py` | Local Hugging Face Sentence Transformers (`all-MiniLM-L6-v2`) embedding engine. | `SentenceTransformerEmbeddings`, `embedding_provider` | **KEEP** | Fast, local offline 384-dimensional dense vector embeddings. |
| `src/evaluation/benchmark.py` | Synthetic benchmark execution harness with gold test queries. | `BenchmarkRunner`, `benchmark_runner` | **REPLACE** | Evaluation harness is slated for complete overhaul in future phases. |
| `src/evaluation/rag_evaluator.py` | IR metrics calculator (Recall@K, MRR, nDCG, Faithfulness). | `RAGEvaluator`, `rag_evaluator` | **REPLACE** | Slated for replacement alongside the evaluation harness. |
| `src/generation/generator.py` | Grounded multi-provider generation engine (Gemini, OpenAI, Anthropic, local extractive). | `GroundedGenerator`, `generator` | **REFACTOR** | Decouple external provider baggage and externalize system prompt. |
| `src/guardrails/injection_guard.py` | Adversarial prompt injection detector using regex patterns and canary isolation. | `PromptInjectionGuard`, `injection_guard` | **KEEP** | Deterministic injection detection verified by tests. |
| `src/guardrails/output_guard.py` | Output PII sanitization and sentence-level context faithfulness verification. | `OutputGuardrail`, `output_guard` | **KEEP** | Enforces zero hallucination and scrubs generated answers before client dispatch. |
| `src/guardrails/pii_guard.py` | Regex-based PII detector and redactor for emails, phones, SSNs, PAN, Aadhaar, API keys. | `PIIGuard`, `pii_guard` | **KEEP** | Core deterministic P0 guardrail engine masking sensitive identifiers. |
| `src/ingestion/chunkers.py` | Multi-level text splitters (Character, Recursive, Markdown, Semantic, Propositional). | `BaseChunker`, `CharacterSplitter`, `RecursiveCharacterSplitter`, `DocumentSpecificSplitter`, `SemanticSplitter`, `PropositionalSplitter`, `ChunkerFactory` | **KEEP** | Thoroughly tested, robust chunking strategies (Levels 1–5). |
| `src/ingestion/parsers.py` | Plain text and Markdown document content extractors. | `BaseParser`, `TextParser`, `MarkdownParser`, `DocumentParserFactory` | **KEEP** | Clean document parsing abstractions. |
| `src/knowledge_graph/graph_store.py` | NetworkX-based entity-relation extraction and traversal engine. | `KnowledgeGraphEngine`, `knowledge_graph` | **REPLACE** | Slated for removal/replacement in the knowledge graph phase. |
| `src/pipeline/rag_pipeline.py` | Primary RAG orchestrator coordinating input guardrails, hybrid search, generation, and output check. | `RAGPipeline`, `rag_pipeline` | **KEEP** | Central tested execution engine with calibrated abstention. |
| `src/retrieval/bm25_search.py` | Sparse lexical keyword retrieval using `rank_bm25.BM25Okapi`. | `BM25SearchEngine`, `bm25_engine` | **KEEP** | Essential exact-match retrieval component. |
| `src/retrieval/deduplicator.py` | Context deduplication using 3-shingle Jaccard overlap thresholding. | `ContextDeduplicator`, `deduplicator` | **KEEP** | Context window optimization eliminating duplicate passages. |
| `src/retrieval/hybrid_search.py` | Reciprocal Rank Fusion (RRF) combining dense and sparse candidate rankings. | `HybridSearchEngine`, `hybrid_search` | **KEEP** | Proven rank fusion mechanism uniting heterogeneous distributions. |
| `src/retrieval/hyde.py` | Hypothetical Document Embeddings (HyDE) query expansion generator. | `HyDERewriter`, `hyde_rewriter` | **KEEP** | Bridges semantic gap for terse queries. |
| `src/retrieval/reranker.py` | Neural cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`). | `NeuralCrossEncoderReranker`, `reranker` | **KEEP** | Neural joint cross-attention reranking for high Top-K precision. |
| `src/schemas/auth_models.py` | Strict Pydantic models for authentication, OTP, JWT tokens, and user profiles (`extra="forbid"`). | `StrictBaseModel`, `OTPRequest`, `OTPVerifyRequest`, `UserResponse`, `TokenResponse`, `OTPResponse`, `MessageResponse` | **KEEP** | Strict validation contracts for passwordless authentication. |
| `src/schemas/models.py` | Strict Pydantic models for documents, search, guardrails, and RAG requests/responses (`extra="forbid"`). | `StrictBaseModel`, `SearchMode`, `ChunkingStrategy`, `DocumentChunk`, `ScoredChunk`, `Citation`, `PIIEntityInfo`, `GuardrailReport`, `RAGRequest`, `RAGResponse`, `SearchRequest`, `SearchResponse`, `DocumentIngestRequest`, `DocumentIngestResponse`, `ChunkPreviewRequest`, `ChunkPreviewResponse`, `GuardrailCheckRequest`, `GuardrailCheckResponse`, `GuardrailAuditRequest`, `GuardrailAuditResponse`, `BenchmarkResponse`, `GraphResponse`, `HealthResponse` | **KEEP** | Strict API schemas preventing unexpected fields. |
| `src/static/app.js` | Client-side JavaScript handling login wall, 6-digit OTP UI, in-memory tokens, and RAG dashboard. | Frontend script | **REPLACE** | Slated for modernization in the dedicated frontend phase. |
| `src/static/index.html` | Client HTML markup containing login template, dashboard template, and app mounting point. | Frontend template | **REPLACE** | Slated for modernization in the dedicated frontend phase. |
| `src/static/styles.css` | Client styling for login wall card, OTP inputs, and dashboard layout. | Frontend stylesheet | **REPLACE** | Slated for modernization in the dedicated frontend phase. |
| `src/vectorstore/chroma_store.py` | Persistent local ChromaDB collection wrapper for vector embedding storage and retrieval. | `ChromaVectorStore`, `vector_store` | **KEEP** | Stable local vector database with metadata filtering. |

---

## 3. API Route Inventory

| HTTP Method | Route Path | Auth Dependency | Request Model | Response Model |
|---|---|---|---|---|
| `GET` | `/healthz` | None (Public) | None | `dict` (`{"status": "healthy"}`) |
| `GET` | `/` | None (Public) | None | `FileResponse` / `dict` |
| `GET` | `/api/v1/health` | None (Public) | None | `HealthResponse` |
| `GET` | `/api/v1/metrics` | None (Public) | None | `dict` |
| `POST` | `/api/v1/auth/request-otp` | None (Public) | `OTPRequest` | `OTPResponse` |
| `POST` | `/api/v1/auth/verify-otp` | None (Public) | `OTPVerifyRequest` | `TokenResponse` |
| `POST` | `/api/v1/auth/refresh` | None (Public; reads `refresh_token` cookie) | None | `TokenResponse` |
| `POST` | `/api/v1/auth/logout` | None (Public; clears cookie) | None | `MessageResponse` |
| `GET` | `/api/v1/auth/me` | `Depends(get_current_user)` | None | `UserResponse` |
| `POST` | `/api/v1/documents/ingest` | `Depends(get_current_user)` | `DocumentIngestRequest` | `DocumentIngestResponse` |
| `POST` | `/api/v1/documents/preview-chunking` | `Depends(get_current_user)` | `ChunkPreviewRequest` | `ChunkPreviewResponse` |
| `POST` | `/api/v1/documents/reset` | `Depends(get_current_user)` | None | `MessageResponse` |
| `POST` | `/api/v1/search` | `Depends(get_current_user)` | `SearchRequest` | `SearchResponse` |
| `POST` | `/api/v1/rag/query` | `Depends(get_current_user)` | `RAGRequest` | `RAGResponse` |
| `POST` | `/api/v1/guardrails/check` | `Depends(get_current_user)` | `GuardrailCheckRequest` | `GuardrailCheckResponse` |
| `POST` | `/api/v1/guardrails/audit` | `Depends(get_current_user)` + `X-Audit-Token` Header | `GuardrailAuditRequest` | `GuardrailAuditResponse` |
| `GET` | `/api/v1/graph` | `Depends(get_current_user)` | None | `GraphResponse` |
| `POST` | `/api/v1/evaluations/benchmark` | `Depends(get_current_user)` | None | `BenchmarkResponse` |

---

## 4. Request Flow for `/api/v1/rag/query`

When an authenticated user issues a query to `/api/v1/rag/query`, execution follows this sequential call chain:

1. **`src/api/main.py:add_process_time_and_request_id`**
   - Intercepts incoming HTTP request, reads or generates `X-Request-ID` UUID, and starts the timer.
2. **`src/api/deps.py:get_current_user`**
   - Extracts Bearer token from `Authorization` header.
   - Calls `src/auth/jwt_handler.py:decode_access_token` to verify pinned HS256 algorithm and validate claims (`exp`, `sub`, `iss`, `aud`).
   - Calls `src/auth/store.py:AuthStore.get_user_by_id` to verify user exists and session is active.
3. **`src/api/v1/rag.py:query_rag_pipeline`**
   - Receives validated `RAGRequest` and injected `RAGPipeline` dependency.
   - Delegates directly to `rag_pipeline.run(request)`.
4. **`src/pipeline/rag_pipeline.py:RAGPipeline.run`**
   - Orchestrates the four-stage RAG lifecycle:
5. **`src/guardrails/injection_guard.py:PromptInjectionGuard.evaluate`**
   - Evaluates query against regex jailbreak signatures and canary boundary indicators. Returns threat verdict, score, and pattern matches.
6. **`src/guardrails/pii_guard.py:PIIGuard.redact`**
   - If `guardrails_enabled` is true, scans query for sensitive entities (emails, phones, SSNs, PAN, Aadhaar, API keys) and replaces them with redaction tokens (`[EMAIL_REDACTED]`, etc.).
   - If prompt injection is detected, increments metric `guardrail_injection_blocked` and returns early with `status="abstained"`.
7. **`src/retrieval/hybrid_search.py:HybridSearchEngine.search`**
   - Executes multi-stage candidate retrieval using sanitized query:
   - 7a. `src/retrieval/hyde.py:HyDERewriter.get_hyde_embedding` (if `use_hyde=True`) OR `src/embeddings/provider.py:SentenceTransformerEmbeddings.encode` (produces 384-d normalized vector).
   - 7b. `src/vectorstore/chroma_store.py:ChromaVectorStore.query_dense` (dense cosine search in ChromaDB).
   - 7c. `src/retrieval/bm25_search.py:BM25SearchEngine.search` (sparse tokenized lexical search).
   - 7d. `src/retrieval/hybrid_search.py:HybridSearchEngine._reciprocal_rank_fusion` (combines candidate ranks using formula $RRF = \sum \frac{1}{k + rank}$).
   - 7e. `src/retrieval/reranker.py:NeuralCrossEncoderReranker.rerank` (if `use_reranker=True`, scores query-chunk pairs with cross-encoder).
   - 7f. `src/retrieval/deduplicator.py:ContextDeduplicator.deduplicate` (filters overlapping passages using 3-shingle Jaccard similarity threshold 0.70).
8. **Relevance Threshold Guard**
   - Filters chunks by `final_score >= settings.RELEVANCE_THRESHOLD` (0.15). If no chunks qualify, returns early with `status="abstained"` and `is_grounded=False`.
9. **`src/generation/generator.py:GroundedGenerator.generate`**
   - Constructs grounded prompt with numbered citations `[1]`, `[2]`.
   - Dispatches to configured provider (`_call_gemini`, `_call_openai`, `_call_anthropic`, `_call_local_hf`, or `_local_grounded_synthesis`).
   - If grounded answer cannot be formed or lacks citations, returns `is_grounded=False`, prompting pipeline abstention.
10. **`src/guardrails/output_guard.py:OutputGuardrail.sanitize_output`**
    - Scans generated answer to guarantee no PII leaked into the response text.
11. **`src/guardrails/output_guard.py:OutputGuardrail.check_faithfulness`**
    - Verifies that claim sentences in generated answer are supported by context passages. If `faithfulness < 0.50`, abstains with `status="abstained"`.
12. **`src/embeddings/provider.py:SentenceTransformerEmbeddings.encode`**
    - Computes cosine similarity between sanitized query embedding and answer embedding to determine semantic relevance score.
13. **`src/core/metrics.py:MetricsTracker.record_latency`**
    - Records `rag_pipeline_latency` histogram.
14. **`src/api/main.py:add_process_time_and_request_id`**
    - Appends `X-Request-ID` and `X-Process-Time-MS` response headers, returning serialized `RAGResponse`.

---

## 5. Configuration & Environment Variables

The table below lists all configuration variables defined in `src/core/config.py` along with their default values. Secrets must be supplied via `.env` or system environment; defaults for secrets are empty or None.

| Environment Variable Name | Default Value | Description |
|---|---|---|
| `PROJECT_NAME` | `"SafeStrata: Layered Hybrid RAG & Guardrails Engine"` | Application title for OpenAPI docs |
| `PROJECT_VERSION` | `"1.0.0"` | Application semver string |
| `API_V1_STR` | `"/api/v1"` | API v1 URL path prefix |
| `DEBUG` | `False` | Verbose debug mode flag |
| `HOST` | `"0.0.0.0"` | Server listening bind address |
| `PORT` | `8001` | Server listening bind port |
| `ALLOWED_ORIGINS` | `["*"]` | CORS allowed origins list |
| `EMBEDDING_MODEL` | `"all-MiniLM-L6-v2"` | SentenceTransformer dense embedding model |
| `RERANKER_MODEL` | `"cross-encoder/ms-marco-MiniLM-L-6-v2"` | Neural Cross-Encoder reranking model |
| `EMBEDDING_DIMENSION` | `384` | Embedding vector dimensionality |
| `CHROMA_PERSIST_DIR` | `"<BASE_DIR>/data/chroma"` | Persistent ChromaDB filesystem directory |
| `DEFAULT_COLLECTION_NAME`| `"enterprise_knowledge"` | ChromaDB vector collection name |
| `RRF_K` | `60` | Reciprocal Rank Fusion smoothing parameter |
| `DEFAULT_TOP_K` | `5` | Default number of passages returned to generator |
| `DEFAULT_RETRIEVAL_LIMIT`| `15` | Pre-fusion candidate pool size per retrieval leg |
| `HYBRID_ALPHA` | `0.5` | Weight between dense and sparse ranks |
| `GUARDRAILS_ENABLED` | `True` | Master toggle for guardrails |
| `INJECTION_DETECTION_THRESHOLD` | `0.65` | Prompt injection detection sensitivity threshold |
| `PII_REDACTION_ENABLED` | `True` | Toggle for automatic PII redaction |
| `CANARY_TOKEN_PREFIX` | `"SEC_CTX"` | Isolation canary boundary token tag |
| `AUDIT_TOKEN` | `"safestrata-audit-secret-token"` | Required token header for guardrail rule audits |
| `LLM_PROVIDER` | `"local"` | Active generative provider (`local`, `gemini`, `openai`, `anthropic`) |
| `OPENAI_API_KEY` | `""` | OpenAI API key (optional) |
| `GEMINI_API_KEY` | `""` | Google Gemini API key (optional) |
| `ANTHROPIC_API_KEY` | `""` | Anthropic Claude API key (optional) |
| `LOCAL_LLM_MODEL` | `"Qwen/Qwen2.5-0.5B-Instruct"` | Local Hugging Face generative model identifier |
| `LLM_MODEL_NAME` | `"gpt-4o-mini"` | Upstream model name for external providers |
| `LLM_TEMPERATURE` | `0.2` | Generation sampling temperature |
| `RELEVANCE_THRESHOLD` | `0.15` | Minimum score required for passage grounding |
| `APP_ENV` | `"development"` | Runtime environment (`development`, `production`, `test`) |
| `JWT_SECRET` | `None` *(Refuses startup if empty)* | Cryptographic HMAC secret for access token signing |
| `JWT_ALGORITHM` | `"HS256"` | Pinned JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token time-to-live |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token cookie time-to-live |
| `JWT_ISSUER` | `"safestrata-auth"` | JWT `iss` claim |
| `JWT_AUDIENCE` | `"safestrata-app"` | JWT `aud` claim |
| `OTP_PEPPER` | `"safestrata-otp-server-pepper-secret-2026"` | HMAC secret for hashing OTP verification codes |
| `OTP_EXPIRE_MINUTES` | `10` | Lifetime of an issued OTP code |
| `OTP_MAX_ATTEMPTS` | `5` | Maximum failed verification attempts before invalidation |
| `OTP_RESEND_COOLDOWN_SECONDS` | `60` | Cooldown period before new OTP can be requested |
| `SMTP_HOST` | `None` | Outgoing SMTP server hostname |
| `SMTP_PORT` | `587` | Outgoing SMTP server port |
| `SMTP_USERNAME` | `None` | SMTP authentication username |
| `SMTP_PASSWORD` | `None` | SMTP authentication password / App password |
| `SMTP_FROM` | `"no-reply@safestrata.local"` | Default From header address on outgoing emails |
| `SMTP_STARTTLS` | `True` | Enable explicit STARTTLS upgrade |
| `SMTP_SSL` | `False` | Enable implicit SSL connection |
| `SMTP_TIMEOUT_SECONDS` | `10.0` | Socket timeout for SMTP network transactions |
| `GRAPH_STORAGE_PATH` | `"<BASE_DIR>/data/knowledge_graph.json"` | Filesystem storage path for NetworkX knowledge graph |
| `ENABLE_GRAPH_ENRICHMENT`| `True` | Toggle for knowledge graph entity enrichment |

---

## 6. Data Stores & Synchronization Architecture

### Store Topography
1. **Users, OTPs & Refresh Token Families**
   - **Location**: In-memory heap inside `src/auth/store.py:AuthStore` (`auth_store` singleton).
   - **Structures**:
     - `users`: `Dict[str, UserRecord]` (keyed by email; secondary index by user UUID).
     - `otps`: `Dict[str, OTPRecord]` (keyed by email; stores HMAC-SHA256 peppered hash, expiration timestamp, attempt counter).
     - `refresh_tokens`: `Dict[str, RefreshTokenRecord]` (keyed by token string; maps to user ID, family ID, expiration).
     - `revoked_families`: `Set[str]` (set of family IDs revoked upon reuse detection).
   - **Concurrency**: Protected by re-entrant mutex (`threading.RLock`).
2. **Dense Vector Chunks & Embeddings**
   - **Location**: Disk-persisted SQLite and HNSW binary indices managed by ChromaDB at `data/chroma`.
   - **Structures**: Document chunk strings, 384-dimensional dense vectors, metadata attributes (`document_id`, `chunk_index`, offsets).
   - **Concurrency**: Handled by internal ChromaDB connection pool and SQLite transactional locking.
3. **Sparse BM25 Inverted Index**
   - **Location**: In-memory heap inside `src/retrieval/bm25_search.py:BM25SearchEngine` (`bm25_engine` singleton).
   - **Structures**: In-memory lists `chunks: List[ScoredChunk]`, tokenized `corpus: List[List[str]]`, and `rank_bm25.BM25Okapi` object.
   - **Concurrency**: Protected by re-entrant mutex (`threading.RLock`).
4. **Knowledge Graph**
   - **Location**: Disk JSON file at `data/knowledge_graph.json`, parsed into a NetworkX `Graph` in `src/knowledge_graph/graph_store.py:KnowledgeGraphEngine`.

### Synchronization Mechanism & Lifecycle
- **Ingestion Sync**:
  - In `src/api/v1/documents.py:ingest_document`, when a document is uploaded:
    1. Chunks are generated via `ChunkerFactory`.
    2. Chunks and dense embeddings are persisted to ChromaDB via `vector_store.add_chunks()`.
    3. The identical chunk instances are immediately indexed in-memory via `bm25_engine.index_chunks()`.
- **Reset Sync**:
  - In `/api/v1/documents/reset`, `vector_store.reset()` deletes all ChromaDB collections and `bm25_engine.reset()` clears all in-memory BM25 corpus structures.
- **Boot Synchronization Gap**:
  - ChromaDB persists chunks on disk across server restarts, but `BM25SearchEngine` and `AuthStore` exist in memory only. On cold boot, BM25 starts empty until re-seeded or ingested. Persistent synchronization for the sparse index and user accounts is flagged for the persistence phase.

---

## 7. Test Inventory

| Test File | What It Covers | What It Does NOT Cover |
|---|---|---|
| `tests/conftest.py` | Fixture initialization and test environment variable provisioning (`APP_ENV=test`, `JWT_SECRET`, `OTP_PEPPER`). | Test client definitions, mock mailer instances. |
| `tests/test_api.py` | Health endpoint, guardrails check route, chunk previewing, document ingestion, hybrid search, HyDE, reranker, benchmark route, metrics, and reset route with authenticated headers. | Concurrency load testing, malformed multipart uploads, 422 schema validation errors, SSE streaming. |
| `tests/test_auth.py` | Genuine SMTP delivery via mock SMTP server, OTP redaction in logs/JSON, new user auto-provisioning, httpOnly refresh cookie, identical responses for existing/new emails, invalid OTP codes, attempt exhaustion (5 attempts), expired codes, reused codes, 60s cooldown, refresh token rotation, replay attack family revocation, tampered/expired JWT claims, production unconfigured SMTP failure, 401 on protected endpoints, and DOM template isolation. | Multi-node cluster cookie replication, persistent DB state across process restarts, SMS OTP fallback, OAuth2/OIDC social federation. |
| `tests/test_chunkers.py` | CharacterSplitter (fixed length with overlap), RecursiveCharacterSplitter (separator hierarchy), DocumentSpecificSplitter (Markdown headers, tables, code blocks), SemanticSplitter (embedding distance breakpoints), PropositionalSplitter (proposition decomposition), and ChunkerFactory. | Binary PDF/DOCX parsing, OCR extraction, audio/video transcripts, documents exceeding 10MB. |
| `tests/test_generator_providers.py` | Respx-mocked HTTP calls to upstream LLMs: Gemini (success, 403, 429, timeout), OpenAI (success, 401, 429), Anthropic (success, 500), and local extractive synthesis fallback. | Live paid API calls against upstream endpoints, multi-turn chat history context, function calling / tool use. |
| `tests/test_guardrails.py` | Unit tests for `pii_guard.detect` and `pii_guard.redact` (emails, phones, SSNs, API keys), `injection_guard.evaluate` (clean vs attack queries, jailbreak score, pattern match), and `output_guard.check_faithfulness` (grounded vs hallucinated answers). | Obfuscated prompt injections (Base64, ROT13, unicode smuggling), multilingual PII formats, image/audio PII redaction. |
| `tests/test_guardrails_security_p0.py` | P0 security verification: raw PII never in API response JSON, raw PII never in structured logs, raw PII never in LLM prompt, public endpoint hides internal regex patterns, authenticated audit endpoint requires `X-Audit-Token` and Bearer token, guardrails fail when disabled, and out-of-domain queries return `status="abstained"`. | Process memory dump inspection, network packet sniffing, hardware timing attacks. |
| `tests/test_knowledge_graph.py` | Entity and relation extraction from text, graph traversal, and enrichment context generation. | Scalability beyond 10,000 nodes, Neo4j / Cypher graph database queries, visual graph layout rendering. |
| `tests/test_retrieval.py` | BM25 indexing and lexical search, HyDE query expansion generation, canary token wrapping and unwrap validation, and context deduplication via 3-shingle Jaccard overlap. | Approximate Nearest Neighbor (ANN) HNSW recall trade-offs, vector quantization (PQ/SQ), distributed index sharding. |

---

## 8. Known Issues & Technical Debt

1. **Decoupled Knowledge Graph**:
   - `src/knowledge_graph/graph_store.py` provides entity extraction and graph building, but `src/pipeline/rag_pipeline.py:run()` does not incorporate graph traversal into its generation context. It exists as an isolated component with a dedicated inspect endpoint (`/api/v1/graph`).
2. **Volatile In-Memory Stores**:
   - `src/auth/store.py` (`AuthStore`) and `src/retrieval/bm25_search.py` (`BM25SearchEngine`) reside entirely in process memory. A process restart resets all active sessions, user accounts, and BM25 index data while ChromaDB retains persisted chunks.
3. **Hardcoded Fallbacks and Security Tokens**:
   - Default audit token `"safestrata-audit-secret-token"` and default OTP pepper `"safestrata-otp-server-pepper-secret-2026"` are defined as string defaults in `src/core/config.py`.
   - The grounding system prompt (lines 83–88 in `src/generation/generator.py`) is hardcoded inline within the generator method rather than maintained in a configurable prompt template module.
4. **Empty Directories & Artifact Leftovers**:
   - `config/` at the project root is an empty directory (configuration is handled by `src/core/config.py`).
   - `src/ingestion/chunkers/` is an empty directory alongside `src/ingestion/chunkers.py`.
5. **Static Benchmark Dataset**:
   - `src/evaluation/benchmark.py` relies on a static, synthetic gold question dataset ($N=40$). Metric calculations reflect this fixed evaluation set rather than continuous real-world evaluation telemetry.
