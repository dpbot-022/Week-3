# SafeStrata - System Architecture & Component Design

## 1. System Components

The system follows a clean, decoupled layered architecture:

```text
src/
├── api/                  # HTTP Layer (FastAPI Routers, Middleware, Dependencies)
│   ├── v1/               # Health, Documents, Search, RAG, Guardrails, Graph, Evaluations
│   └── main.py           # Application Entrypoint, CORS, Static UI, Lifespan
├── core/                 # Foundation (Config, Structured Logging, Metrics)
├── schemas/              # Pydantic v2 domain models & validation schemas
├── ingestion/            # Parsers & 5-Level Document Chunkers
├── embeddings/           # Local Hugging Face SentenceTransformers Provider
├── vectorstore/          # ChromaDB Persistent Vector Repository
├── retrieval/            # BM25 Sparse Index, RRF Fusion, Cross-Encoder Reranker, HyDE, Dedup
├── knowledge_graph/      # NetworkX Entity Extraction, Graph Modeling & Traversal
├── guardrails/           # PII Scanner & Redactor, Prompt Injection Guard, Output Validator
├── generation/           # Grounded Generator (OpenAI / Local Extractive Synthesizer)
├── evaluation/           # RAG Triad Evaluator & Automated Benchmark Matrix
├── pipeline/             # Full Orchestrator Service
└── static/               # Modern Responsive Web Playground (HTML5, Vanilla CSS, JS)
```

## 2. Component Interactions & Request Lifecycle

1. **Ingress**: Request received via FastAPI. Middleware assigns unique `X-Request-ID` and starts process timer.
2. **Security Gate**:
   - `PromptInjectionGuardrail` evaluates user query against threat heuristics and canary boundaries.
   - `PIIGuardrail` scans and masks emails, phones, SSNs, credit cards, API keys, and IP addresses.
3. **Retrieval**:
   - `HyDEQueryRewriter` generates hypothetical document expansion if enabled.
   - `ChromaVectorStore` executes dense k-NN search using `all-MiniLM-L6-v2`.
   - `BM25SearchEngine` executes sparse lexical search using `BM25Okapi`.
   - `HybridSearchEngine` computes Reciprocal Rank Fusion ($k=60$).
4. **Relational Enrichment**: `KnowledgeGraphEngine` identifies query entities and extracts multi-hop relationship facts from the NetworkX directed graph.
5. **Neural Reranking**: `CrossEncoderReranker` scores query-document pairs with `ms-marco-MiniLM-L-6-v2`.
6. **Context Deduplication**: `ContextDeduplicator` eliminates redundant text passages.
7. **Synthesis**: `GroundedGenerator` formats context with numeric citations `[1]`, `[2]` and answers the query.
8. **Egress Guardrails**: `OutputGuardrail` confirms answer sentences are grounded in source passages (faithfulness check) and ensures no internal PII leaked.
9. **Telemetry**: Response returned with latency breakdown across all pipeline stages.
