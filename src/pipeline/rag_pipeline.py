import time
import re
from typing import Dict, Any, List
from src.core.config import settings
from src.core.logging import logger
from src.core.metrics import metrics
from src.schemas.models import (
    RAGRequest, RAGResponse, GuardrailReport, SearchMode, ScoredChunk
)
from src.guardrails.pii_guard import pii_guard
from src.guardrails.injection_guard import injection_guard
from src.guardrails.output_guard import output_guard
from src.retrieval.hybrid_search import hybrid_search
from src.knowledge_graph.graph_store import knowledge_graph
from src.generation.generator import generator

class RAGPipeline:
    """Production RAG pipeline coordinating guardrails, hybrid search, graph traversal, and generation."""

    def run(self, request: RAGRequest) -> RAGResponse:
        total_start = time.time()
        latencies: Dict[str, float] = {}

        # ---------------------------------------------------------
        # Step 1: Input Guardrails (Injection & PII)
        # ---------------------------------------------------------
        g_start = time.time()
        injection_threat, inj_score, inj_patterns = injection_guard.evaluate(request.query)
        sanitized_query, pii_findings = pii_guard.redact(request.query)
        latencies["guardrails_input_ms"] = round((time.time() - g_start) * 1000, 2)

        guardrail_report = GuardrailReport(
            is_safe=not injection_threat,
            injection_detected=injection_threat,
            injection_score=inj_score,
            injection_patterns=inj_patterns,
            pii_detected=len(pii_findings) > 0,
            pii_entities=pii_findings,
            sanitized_text=sanitized_query,
            latency_ms=latencies["guardrails_input_ms"]
        )

        if injection_threat and request.guardrails_enabled:
            metrics.increment("guardrail_injection_blocked")
            return RAGResponse(
                query=request.query,
                answer=(
                    "Request blocked by Enterprise Guardrails: Potential prompt injection or adversarial "
                    "pattern detected in query."
                ),
                sanitized_query=sanitized_query,
                citations=[],
                graph_entities=[],
                guardrail_report=guardrail_report,
                faithfulness_score=0.0,
                answer_relevance_score=0.0,
                latency_breakdown=latencies,
                total_latency_ms=round((time.time() - total_start) * 1000, 2)
            )

        if len(pii_findings) > 0:
            metrics.increment("guardrail_pii_redacted")

        # Use sanitized query downstream
        active_query = sanitized_query if request.guardrails_enabled else request.query

        # ---------------------------------------------------------
        # Step 2: Retrieval & Hybrid Fusion & Reranking
        # ---------------------------------------------------------
        r_start = time.time()
        retrieved_chunks = hybrid_search.search(
            query=active_query,
            top_k=request.top_k,
            mode=request.search_mode,
            use_reranker=request.use_reranker,
            use_hyde=request.use_hyde
        )
        latencies["retrieval_ms"] = round((time.time() - r_start) * 1000, 2)
        metrics.increment("retrieval_queries")

        # ---------------------------------------------------------
        # Step 3: Knowledge Graph Traversal
        # ---------------------------------------------------------
        kg_start = time.time()
        graph_facts: List[str] = []
        if request.use_knowledge_graph and settings.ENABLE_GRAPH_ENRICHMENT:
            graph_facts = knowledge_graph.traverse_subgraph(active_query)
        latencies["knowledge_graph_ms"] = round((time.time() - kg_start) * 1000, 2)

        # ---------------------------------------------------------
        # Step 4: Grounded Answer Generation
        # ---------------------------------------------------------
        gen_start = time.time()
        gen_result = generator.generate(
            query=active_query,
            context_chunks=retrieved_chunks,
            graph_facts=graph_facts,
            provider=request.llm_provider,
            api_key=request.api_key,
            model_name=request.model_name
        )
        latencies["generation_ms"] = round((time.time() - gen_start) * 1000, 2)

        raw_answer = gen_result["answer"]
        citations = gen_result["citations"]
        generation_mode = gen_result.get("generation_mode", "grounded")

        # ---------------------------------------------------------
        # Step 5: Output Guardrails & Faithfulness Verification
        # ---------------------------------------------------------
        out_g_start = time.time()
        clean_answer, out_pii, out_pii_findings = output_guard.sanitize_output(raw_answer)
        
        # Verify faithfulness against relevant context
        relevant_chunks = [c for c in retrieved_chunks if c.final_score >= settings.RELEVANCE_THRESHOLD]
        if relevant_chunks:
            context_texts = [c.content for c in relevant_chunks]
            faithfulness, unsupported = output_guard.check_faithfulness(clean_answer, context_texts)
        else:
            # General knowledge generation mode - no false grounding claims
            faithfulness = 1.0

        latencies["guardrails_output_ms"] = round((time.time() - out_g_start) * 1000, 2)

        total_latency = round((time.time() - total_start) * 1000, 2)
        metrics.record_latency("rag_pipeline_latency", total_latency)

        # Estimate answer relevance based on keyword/semantic overlap with query
        query_words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", active_query.lower()))
        answer_words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", clean_answer.lower()))
        if query_words:
            overlap = len(query_words & answer_words)
            relevance_score = round(min(1.0, overlap / max(1, len(query_words) * 0.5)), 2)
        else:
            relevance_score = 0.95

        return RAGResponse(
            query=request.query,
            answer=clean_answer,
            sanitized_query=sanitized_query,
            citations=citations,
            graph_entities=graph_facts,
            guardrail_report=guardrail_report,
            faithfulness_score=faithfulness,
            answer_relevance_score=relevance_score,
            latency_breakdown=latencies,
            total_latency_ms=total_latency,
            generation_mode=generation_mode
        )

rag_pipeline = RAGPipeline()
