from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
import uuid

class StrictBaseModel(BaseModel):
    """Base model strictly forbidding extra/undeclared fields to prevent data leaks."""
    model_config = ConfigDict(extra="forbid")

class ChunkingStrategy(str, Enum):
    CHARACTER = "character"
    RECURSIVE = "recursive"
    DOCUMENT_SPECIFIC = "document_specific"
    SEMANTIC = "semantic"
    AGENTIC = "agentic"

class SearchMode(str, Enum):
    HYBRID = "hybrid"
    DENSE = "dense"
    SPARSE = "sparse"

class Chunk(StrictBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    content: str
    chunk_index: int
    strategy: ChunkingStrategy
    metadata: Dict[str, Any] = Field(default_factory=dict)
    character_count: int = 0
    token_estimate: int = 0
    char_start: int = 0
    char_end: int = 0

class IngestDocumentRequest(StrictBaseModel):
    title: str = "Untitled Document"
    content: str
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 400
    chunk_overlap: int = 40
    metadata: Dict[str, Any] = Field(default_factory=dict)

class IngestResponse(StrictBaseModel):
    document_id: str
    title: str
    strategy: ChunkingStrategy
    chunk_count: int
    chunks: List[Chunk]
    entities_extracted: int = 0
    latency_ms: float

class ChunkPreviewRequest(StrictBaseModel):
    text: str
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 350
    chunk_overlap: int = 35

class ChunkPreviewResponse(StrictBaseModel):
    strategy: ChunkingStrategy
    chunk_count: int
    chunks: List[Chunk]
    latency_ms: float

class ScoredChunk(StrictBaseModel):
    id: str
    document_id: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None
    final_score: float
    char_start: int = 0
    char_end: int = 0

class SearchRequest(StrictBaseModel):
    query: str
    top_k: int = 5
    mode: SearchMode = SearchMode.HYBRID
    use_reranker: bool = True
    use_hyde: bool = False
    filter_metadata: Optional[Dict[str, Any]] = None

class SearchResponse(StrictBaseModel):
    query: str
    transformed_query: Optional[str] = None
    mode: SearchMode
    results: List[ScoredChunk]
    total_candidates: int
    reranked: bool
    latency_ms: float

class PIIEntityInfo(StrictBaseModel):
    entity_type: str
    start: int
    end: int
    count: int = 1

class GuardrailReport(StrictBaseModel):
    """Public guardrail response: returns verdict, generic reason, and PII offset counts (never raw values)."""
    is_safe: bool = True
    injection_detected: bool = False
    injection_score: float = 0.0
    reason: Optional[str] = None
    pii_detected: bool = False
    pii_entities: List[PIIEntityInfo] = Field(default_factory=list)
    sanitized_text: str
    latency_ms: float = 0.0

class GuardrailAuditReport(StrictBaseModel):
    """Authenticated audit response: includes matched internal rule names and pattern details."""
    is_safe: bool = True
    injection_detected: bool = False
    injection_score: float = 0.0
    reason: Optional[str] = None
    injection_patterns: List[str] = Field(default_factory=list)
    pii_detected: bool = False
    pii_entities: List[PIIEntityInfo] = Field(default_factory=list)
    sanitized_text: str
    latency_ms: float = 0.0

class GuardrailCheckRequest(StrictBaseModel):
    text: str
    check_pii: bool = True
    check_injection: bool = True

class RAGRequest(StrictBaseModel):
    query: str
    top_k: int = 5
    search_mode: SearchMode = SearchMode.HYBRID
    use_reranker: bool = True
    use_hyde: bool = False
    guardrails_enabled: bool = True
    llm_provider: Optional[str] = None  # "local", "gemini", "openai", "anthropic", "synthesis"
    api_key: Optional[str] = None
    model_name: Optional[str] = None

class GraphNode(StrictBaseModel):
    id: str
    name: str
    entity_type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)

class GraphEdge(StrictBaseModel):
    source: str
    target: str
    relation: str
    weight: float = 1.0

class KnowledgeGraphResponse(StrictBaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_nodes: int
    total_edges: int

class Citation(StrictBaseModel):
    chunk_id: str
    document_id: str
    snippet: str
    score: float
    rank: int
    char_start: int = 0
    char_end: int = 0

class RAGResponse(StrictBaseModel):
    query: str
    answer: str
    status: str = "answered"  # "answered" or "abstained"
    is_grounded: bool = True
    sanitized_query: str
    citations: List[Citation] = Field(default_factory=list)
    guardrail_report: GuardrailReport
    faithfulness_score: float
    answer_relevance_score: float
    latency_breakdown: Dict[str, float]
    total_latency_ms: float

class HealthResponse(StrictBaseModel):
    status: str
    project: str
    version: str
    embedding_model: str
    reranker_model: str
    indexed_chunks: int
    guardrails_active: bool

class ResetResponse(StrictBaseModel):
    status: str
    message: str

class MetricsResponse(StrictBaseModel):
    counters: Dict[str, int]
    latencies: Dict[str, Dict[str, float]]
    uptime_seconds: float

class BootstrapCI(StrictBaseModel):
    mean: float
    ci_lower: float
    ci_upper: float

class EvaluationItem(StrictBaseModel):
    query_id: str
    query: str
    category: str
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    faithfulness: float
    answer_relevance: float
    latency_ms: float
    status: str

class BenchmarkReport(StrictBaseModel):
    timestamp: str
    git_sha: str
    dataset_hash: str
    dataset_size: int
    test_size: int
    metrics: Dict[str, BootstrapCI]
    latency: Dict[str, float]
    ablations: Dict[str, Dict[str, BootstrapCI]]
