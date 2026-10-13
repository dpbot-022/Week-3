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

class RAGRequest(StrictBaseModel):
    query: str
    top_k: int = 5
    search_mode: SearchMode = SearchMode.HYBRID
    use_reranker: bool = True
    use_hyde: bool = False
    use_knowledge_graph: bool = True
    guardrails_enabled: bool = True
    llm_provider: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None

class Citation(StrictBaseModel):
    chunk_id: str
    document_id: str
    snippet: str
    score: float
    rank: int
    title: str = "Policy Document"
    page_number: int = 1
    char_start: int = 0
    char_end: int = 0
    effective_date: Optional[str] = None

class RAGTrace(StrictBaseModel):
    ranks_before_rerank: List[Dict[str, Any]] = Field(default_factory=list)
    ranks_after_rerank: List[Dict[str, Any]] = Field(default_factory=list)
    scores: Dict[str, float] = Field(default_factory=dict)
    redaction_counts: Dict[str, int] = Field(default_factory=dict)
    guardrail_verdicts: Dict[str, Any] = Field(default_factory=dict)
    per_stage_latency_ms: Dict[str, float] = Field(default_factory=dict)
    model_name: str = ""

class RAGResponse(StrictBaseModel):
    query: str
    answer: str
    status: str = "answered"  # "answered", "abstained", "blocked"
    is_grounded: bool = True
    sanitized_query: str
    citations: List[Citation] = Field(default_factory=list)
    graph_entities: List[str] = Field(default_factory=list)
    guardrail_report: GuardrailReport
    faithfulness_score: float
    answer_relevance_score: float
    latency_breakdown: Dict[str, float]
    total_latency_ms: float
    generation_mode: Optional[str] = "grounded"  # "grounded", "abstention", "scope_greeting", "extractive", "blocked"
    trace: Optional[RAGTrace] = None

class BootstrapCI(StrictBaseModel):
    mean: float
    ci_lower: float
    ci_upper: float

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

class EvaluationItem(StrictBaseModel):
    query_id: Optional[str] = None
    query: str
    category: Optional[str] = None
    ground_truth: Optional[str] = None
    context_precision: float = 0.0
    context_recall: float = 0.0
    recall_at_k: Optional[float] = None
    mrr: Optional[float] = None
    ndcg_at_k: Optional[float] = None
    faithfulness: float = 0.0
    answer_relevance: float = 0.0
    latency_ms: float = 0.0
    retrieval_mode: Optional[str] = "hybrid"
    status: Optional[str] = "answered"

class BenchmarkReport(StrictBaseModel):
    timestamp: str
    git_sha: Optional[str] = None
    dataset_hash: Optional[str] = None
    dataset_size: Optional[int] = None
    test_size: Optional[int] = None
    evaluations: List[EvaluationItem] = Field(default_factory=list)
    metrics: Optional[Dict[str, BootstrapCI]] = None
    latency: Optional[Dict[str, float]] = None
    ablations: Optional[Dict[str, Dict[str, BootstrapCI]]] = None
    aggregate_metrics: Optional[Dict[str, Dict[str, float]]] = None
    best_performing_mode: Optional[str] = None
    analysis: Optional[str] = None
