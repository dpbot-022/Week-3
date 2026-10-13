from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

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

class Chunk(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    content: str
    chunk_index: int
    strategy: ChunkingStrategy
    metadata: Dict[str, Any] = Field(default_factory=dict)
    character_count: int = 0
    token_estimate: int = 0

class IngestDocumentRequest(BaseModel):
    title: str = "Untitled Document"
    content: str
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 400
    chunk_overlap: int = 40
    metadata: Dict[str, Any] = Field(default_factory=dict)

class IngestResponse(BaseModel):
    document_id: str
    title: str
    strategy: ChunkingStrategy
    chunk_count: int
    chunks: List[Chunk]
    entities_extracted: int
    latency_ms: float

class ChunkPreviewRequest(BaseModel):
    text: str
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 350
    chunk_overlap: int = 35

class ScoredChunk(BaseModel):
    id: str
    document_id: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None
    final_score: float

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    mode: SearchMode = SearchMode.HYBRID
    use_reranker: bool = True
    use_hyde: bool = False
    filter_metadata: Optional[Dict[str, Any]] = None

class SearchResponse(BaseModel):
    query: str
    transformed_query: Optional[str] = None
    mode: SearchMode
    results: List[ScoredChunk]
    total_candidates: int
    reranked: bool
    latency_ms: float

class GuardrailReport(BaseModel):
    is_safe: bool = True
    injection_detected: bool = False
    injection_score: float = 0.0
    injection_patterns: List[str] = Field(default_factory=list)
    pii_detected: bool = False
    pii_entities: List[Dict[str, Any]] = Field(default_factory=list)
    sanitized_text: str
    latency_ms: float = 0.0

class GuardrailCheckRequest(BaseModel):
    text: str
    check_pii: bool = True
    check_injection: bool = True

class GraphNode(BaseModel):
    id: str
    name: str
    entity_type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)

class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    weight: float = 1.0

class KnowledgeGraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_nodes: int
    total_edges: int

class RAGRequest(BaseModel):
    query: str
    top_k: int = 5
    search_mode: SearchMode = SearchMode.HYBRID
    use_reranker: bool = True
    use_hyde: bool = False
    use_knowledge_graph: bool = True
    guardrails_enabled: bool = True
    llm_provider: Optional[str] = None  # "local", "gemini", "openai", "anthropic"
    api_key: Optional[str] = None
    model_name: Optional[str] = None

class Citation(BaseModel):
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

class RAGTrace(BaseModel):
    ranks_before_rerank: List[Dict[str, Any]] = Field(default_factory=list)
    ranks_after_rerank: List[Dict[str, Any]] = Field(default_factory=list)
    scores: Dict[str, float] = Field(default_factory=dict)
    redaction_counts: Dict[str, int] = Field(default_factory=dict)
    guardrail_verdicts: Dict[str, Any] = Field(default_factory=dict)
    per_stage_latency_ms: Dict[str, float] = Field(default_factory=dict)
    model_name: str = ""

class RAGResponse(BaseModel):
    query: str
    answer: str
    sanitized_query: str
    citations: List[Citation]
    graph_entities: List[str] = Field(default_factory=list)
    guardrail_report: GuardrailReport
    faithfulness_score: float
    answer_relevance_score: float
    latency_breakdown: Dict[str, float]
    total_latency_ms: float
    generation_mode: Optional[str] = "grounded"  # "grounded", "abstention", "scope_greeting", "extractive"
    trace: Optional[RAGTrace] = None

class EvaluationItem(BaseModel):
    query: str
    ground_truth: Optional[str] = None
    context_precision: float
    context_recall: float
    faithfulness: float
    answer_relevance: float
    latency_ms: float
    retrieval_mode: str

class BenchmarkReport(BaseModel):
    timestamp: str
    evaluations: List[EvaluationItem]
    aggregate_metrics: Dict[str, Dict[str, float]]
    best_performing_mode: str
    analysis: str
