import time
from typing import Dict, Any, List
import numpy as np
from src.core.config import settings
from src.core.logging import logger
from src.core.metrics import metrics
from src.schemas.models import (
    RAGRequest, RAGResponse, GuardrailReport, SearchMode, ScoredChunk, PIIEntityInfo
)
from src.guardrails.pii_guard import pii_guard
from src.guardrails.injection_guard import injection_guard
from src.guardrails.output_guard import output_guard
from src.retrieval.hybrid_search import hybrid_search
from src.generation.generator import generator
from src.embeddings.provider import embedding_provider

class RAGPipeline:
    """Production RAG pipeline coordinating guardrails, hybrid search, neural reranking, and grounded generation."""

    def run(self, request: RAGRequest) -> RAGResponse:
        total_start = time.time()
        latencies: Dict[str, float] = {}

        # ---------------------------------------------------------
        # Step 1: Input Guardrails (Injection & PII)
        # ---------------------------------------------------------
        g_start = time.time()
        injection_threat, inj_score, inj_patterns = injection_guard.evaluate(request.query)
        if request.guardrails_enabled:
            sanitized_query, pii_findings = pii_guard.redact(request.query)
        else:
            sanitized_query = request.query
            pii_findings = []
        latencies["guardrails_input_ms"] = round((time.time() - g_start) * 1000, 2)

        reason = "Potential adversarial prompt injection detected" if injection_threat else None
        pii_entities = [PIIEntityInfo(**f) for f in pii_findings]

        guardrail_report = GuardrailReport(
            is_safe=not injection_threat,
            injection_detected=injection_threat,
            injection_score=inj_score,
            reason=reason,
            pii_detected=len(pii_entities) > 0,
            pii_entities=pii_entities,
            sanitized_text=sanitized_query,
            latency_ms=latencies["guardrails_input_ms"]
        )

        if injection_threat and request.guardrails_enabled:
            metrics.increment("guardrail_injection_blocked")
            return RAGResponse(
                query=sanitized_query,
                answer=(
                    "Request blocked by Enterprise Guardrails: Potential prompt injection or adversarial "
                    "pattern detected in query."
                ),
                status="abstained",
                is_grounded=False,
                sanitized_query=sanitized_query,
                citations=[],
                guardrail_report=guardrail_report,
                faithfulness_score=0.0,
                answer_relevance_score=0.0,
                latency_breakdown=latencies,
                total_latency_ms=round((time.time() - total_start) * 1000, 2)
            )

        if len(pii_findings) > 0:
            metrics.increment("guardrail_pii_redacted")

        # Use sanitized query downstream
        active_query = sanitized_query

        # ---------------------------------------------------------
        # Step 2: Retrieval & Hybrid Fusion & Neural Reranking
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

        # Relevance threshold check
        relevant_chunks = [c for c in retrieved_chunks if c.final_score >= settings.RELEVANCE_THRESHOLD]
        if not relevant_chunks:
            total_latency = round((time.time() - total_start) * 1000, 2)
            return RAGResponse(
                query=sanitized_query,
                answer="Abstained: Insufficient grounded context retrieved to answer this query safely.",
                status="abstained",
                is_grounded=False,
                sanitized_query=sanitized_query,
                citations=[],
                guardrail_report=guardrail_report,
                faithfulness_score=0.0,
                answer_relevance_score=0.0,
                latency_breakdown=latencies,
                total_latency_ms=total_latency
            )

        # ---------------------------------------------------------
        # Step 3: Grounded Answer Generation
        # ---------------------------------------------------------
        gen_start = time.time()
        gen_result = generator.generate(
            query=active_query,
            context_chunks=relevant_chunks,
            provider=request.llm_provider,
            api_key=request.api_key,
            model_name=request.model_name
        )
        latencies["generation_ms"] = round((time.time() - gen_start) * 1000, 2)

        raw_answer = gen_result["answer"]
        citations = gen_result.get("citations", [])
        if not gen_result.get("is_grounded", True) or not citations:
            total_latency = round((time.time() - total_start) * 1000, 2)
            return RAGResponse(
                query=sanitized_query,
                answer="Abstained: Insufficient grounded context retrieved to answer this query safely.",
                status="abstained",
                is_grounded=False,
                sanitized_query=sanitized_query,
                citations=[],
                guardrail_report=guardrail_report,
                faithfulness_score=0.0,
                answer_relevance_score=0.0,
                latency_breakdown=latencies,
                total_latency_ms=total_latency
            )

        # ---------------------------------------------------------
        # Step 4: Output Guardrails & Faithfulness Verification
        # ---------------------------------------------------------
        out_g_start = time.time()
        clean_answer, out_pii, out_pii_findings = output_guard.sanitize_output(raw_answer)
        
        context_texts = [c.content for c in relevant_chunks]
        faithfulness, unsupported = output_guard.check_faithfulness(clean_answer, context_texts)
        latencies["guardrails_output_ms"] = round((time.time() - out_g_start) * 1000, 2)

        total_latency = round((time.time() - total_start) * 1000, 2)
        metrics.record_latency("rag_pipeline_latency", total_latency)

        # If faithfulness is below threshold or no citations, abstain
        if faithfulness < 0.50:
            return RAGResponse(
                query=sanitized_query,
                answer="Abstained: Retrieved passages did not sufficiently support a grounded response.",
                status="abstained",
                is_grounded=False,
                sanitized_query=sanitized_query,
                citations=[],
                guardrail_report=guardrail_report,
                faithfulness_score=round(faithfulness, 2),
                answer_relevance_score=0.0,
                latency_breakdown=latencies,
                total_latency_ms=total_latency
            )

        # Compute semantic answer relevance via embedding cosine similarity
        try:
            q_emb = embedding_provider.encode(active_query, normalize=True)
            a_emb = embedding_provider.encode(clean_answer, normalize=True)
            sim = float(np.dot(q_emb, a_emb))
            relevance_score = round(max(0.0, min(1.0, sim)), 2)
        except Exception:
            relevance_score = 0.85

        return RAGResponse(
            query=sanitized_query,
            answer=clean_answer,
            status="answered",
            is_grounded=True,
            sanitized_query=sanitized_query,
            citations=citations,
            guardrail_report=guardrail_report,
            faithfulness_score=round(faithfulness, 2),
            answer_relevance_score=relevance_score,
            latency_breakdown=latencies,
            total_latency_ms=total_latency
        )

rag_pipeline = RAGPipeline()
