import time
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from src.core.config import settings
from src.core.logging import logger
from src.core.metrics import metrics
from src.schemas.models import (
    RAGRequest, RAGResponse, GuardrailReport, SearchMode, ScoredChunk, Citation, RAGTrace, PIIEntityInfo
)
from src.guardrails.pii_guard import pii_guard
from src.guardrails.injection_guard import injection_guard
from src.guardrails.output_guard import output_guard
from src.retrieval.hybrid_search import hybrid_search
from src.knowledge_graph.graph_store import knowledge_graph
from src.generation.generator import grounded_generator
from src.db.session import SessionLocal
from src.db.models import Document, User

class RAGPipeline:
    """Production SafeStrata RAG pipeline enforcing strict server-side policy:
    Normalization -> Input Guardrails -> Intent Routing -> Role-filtered Dense + BM25 ->
    RRF -> Reranking -> Dedup -> Relevance Gating -> Generation -> Citation Check ->
    NLI Verification -> Output Scrubbing -> Trace."""

    def run(self, request: RAGRequest, role: str = "viewer", db: Optional[Session] = None) -> RAGResponse:
        total_start = time.time()
        latencies: Dict[str, float] = {}
        trace_data: Dict[str, Any] = {
            "ranks_before_rerank": [],
            "ranks_after_rerank": [],
            "scores": {},
            "redaction_counts": {},
            "guardrail_verdicts": {},
            "per_stage_latency_ms": {},
            "model_name": settings.OLLAMA_MODEL
        }

        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True

        try:
            # ---------------------------------------------------------
            # Step 1: Query Normalization & Input Guardrails
            # ---------------------------------------------------------
            g_start = time.time()
            clean_query = pii_guard.sanitize_input(request.query.strip())
            injection_threat, inj_score, inj_patterns = injection_guard.evaluate(clean_query)
            sanitized_query, pii_findings = pii_guard.redact(clean_query)
            latencies["guardrails_input_ms"] = round((time.time() - g_start) * 1000, 2)
            trace_data["per_stage_latency_ms"]["input_guardrails"] = latencies["guardrails_input_ms"]
            trace_data["guardrail_verdicts"]["prompt_injection"] = {
                "detected": injection_threat,
                "score": inj_score,
                "patterns": inj_patterns
            }
            trace_data["redaction_counts"]["input_pii_redacted"] = len(pii_findings)

            pii_entities_info = [
                PIIEntityInfo(entity_type=f["entity_type"], start=f["start"], end=f["end"], count=1)
                for f in pii_findings
            ]

            guardrail_report = GuardrailReport(
                is_safe=not injection_threat,
                injection_detected=injection_threat,
                injection_score=inj_score,
                reason="Potential adversarial prompt injection detected" if injection_threat else None,
                pii_detected=len(pii_entities_info) > 0,
                pii_entities=pii_entities_info,
                sanitized_text=sanitized_query,
                latency_ms=latencies["guardrails_input_ms"]
            )

            # Block prompt injection immediately
            if injection_threat:
                metrics.increment("guardrail_injection_blocked")
                total_ms = round((time.time() - total_start) * 1000, 2)
                trace_data["per_stage_latency_ms"]["total"] = total_ms
                return RAGResponse(
                    query=sanitized_query,
                    answer="Request blocked: Potential prompt injection or adversarial pattern detected in query.",
                    status="blocked",
                    is_grounded=False,
                    sanitized_query=sanitized_query,
                    citations=[],
                    graph_entities=[],
                    guardrail_report=guardrail_report,
                    faithfulness_score=0.0,
                    answer_relevance_score=0.0,
                    latency_breakdown=latencies,
                    total_latency_ms=total_ms,
                    generation_mode="blocked",
                    trace=RAGTrace(**trace_data)
                )

            # Fetch user's accessible documents from DB
            all_docs = db.query(Document).all()
            accessible_docs = [d for d in all_docs if role in d.allowed_roles]
            accessible_titles = [d.title for d in accessible_docs]

            # ---------------------------------------------------------
            # Step 2: Intent Routing (Greeting / Scope without LLM)
            # ---------------------------------------------------------
            is_greeting = bool(re.match(
                r"^\s*(hi|hello|hey|greetings|good\s+(morning|afternoon|evening)|what\s+can\s+you\s+do|who\s+are\s+you|help)\s*[.?!]*\s*$",
                sanitized_query,
                re.IGNORECASE
            ))
            if is_greeting:
                if accessible_titles:
                    scope_msg = (
                        f"Hello! I am SafeStrata, your internal compliance and regulatory answer desk. "
                        f"You currently have access to {len(accessible_titles)} policy document(s):\n\n" +
                        "\n".join([f"- {t}" for t in accessible_titles]) +
                        "\n\nAsk any question grounded in these policies, and I will cite exact pages."
                    )
                else:
                    scope_msg = "Hello! I am SafeStrata, your internal compliance desk. You do not currently have access to any policy documents."

                total_ms = round((time.time() - total_start) * 1000, 2)
                latencies["total_ms"] = total_ms
                trace_data["per_stage_latency_ms"]["total"] = total_ms
                return RAGResponse(
                    query=sanitized_query,
                    answer=scope_msg,
                    sanitized_query=sanitized_query,
                    citations=[],
                    graph_entities=[],
                    guardrail_report=guardrail_report,
                    faithfulness_score=1.0,
                    answer_relevance_score=1.0,
                    latency_breakdown=latencies,
                    total_latency_ms=total_ms,
                    generation_mode="scope_greeting",
                    trace=RAGTrace(**trace_data)
                )

            # ---------------------------------------------------------
            # Step 3: Role-Filtered Hybrid Retrieval & Reranking
            # ---------------------------------------------------------
            r_start = time.time()
            retrieved_chunks = hybrid_search.search(
                query=sanitized_query,
                top_k=request.top_k,
                mode=SearchMode.HYBRID,
                use_reranker=True,
                use_hyde=False,
                role=role
            )
            latencies["retrieval_ms"] = round((time.time() - r_start) * 1000, 2)
            trace_data["per_stage_latency_ms"]["retrieval"] = latencies["retrieval_ms"]

            for idx, c in enumerate(retrieved_chunks, start=1):
                trace_data["ranks_after_rerank"].append({
                    "rank": idx,
                    "chunk_id": c.id,
                    "document_id": c.document_id,
                    "score": round(c.final_score, 4),
                    "title": c.metadata.get("title", "Policy"),
                    "page": c.metadata.get("page_number", 1)
                })

            # ---------------------------------------------------------
            # Step 4: Grounded Answer Generation
            # ---------------------------------------------------------
            gen_start = time.time()
            gen_result = grounded_generator.generate(
                query=sanitized_query,
                context_chunks=retrieved_chunks,
                accessible_doc_titles=accessible_titles
            )
            latencies["generation_ms"] = round((time.time() - gen_start) * 1000, 2)
            trace_data["per_stage_latency_ms"]["generation"] = latencies["generation_ms"]

            # Enrich citations with document metadata (page, span, date)
            enriched_citations: List[Citation] = []
            doc_map = {d.id: d for d in accessible_docs}

            for cit in gen_result.get("citations", []):
                doc_obj = doc_map.get(cit.document_id)
                matching_chunk = next((c for c in retrieved_chunks if c.id == cit.chunk_id), None)
                page_num = matching_chunk.metadata.get("page_number", 1) if matching_chunk else 1
                char_start = matching_chunk.metadata.get("char_start", 0) if matching_chunk else 0
                char_end = matching_chunk.metadata.get("char_end", 0) if matching_chunk else 0
                title = doc_obj.title if doc_obj else matching_chunk.metadata.get("title", "Policy Document") if matching_chunk else "Policy Document"
                eff_date = doc_obj.effective_date if doc_obj else None

                enriched_citations.append(Citation(
                    chunk_id=cit.chunk_id,
                    document_id=cit.document_id,
                    snippet=cit.snippet,
                    score=cit.score,
                    rank=cit.rank,
                    title=title,
                    page_number=page_num,
                    char_start=char_start,
                    char_end=char_end,
                    effective_date=eff_date
                ))

            # ---------------------------------------------------------
            # Step 5: Output Guardrail & PII Scrub
            # ---------------------------------------------------------
            out_start = time.time()
            clean_answer, out_pii, out_pii_findings = output_guard.sanitize_output(gen_result["answer"])
            latencies["guardrails_output_ms"] = round((time.time() - out_start) * 1000, 2)
            trace_data["per_stage_latency_ms"]["output_guardrails"] = latencies["guardrails_output_ms"]
            trace_data["redaction_counts"]["output_pii_redacted"] = len(out_pii_findings)

            total_latency = round((time.time() - total_start) * 1000, 2)
            latencies["total_ms"] = total_latency
            trace_data["per_stage_latency_ms"]["total"] = total_latency

            # Trace scores
            trace_data["scores"]["faithfulness"] = gen_result.get("faithfulness_score", 1.0)
            trace_data["scores"]["is_grounded"] = 1.0 if gen_result.get("is_grounded") else 0.0

            is_grounded = gen_result.get("is_grounded", True)
            status = "answered" if is_grounded else "abstained"

            return RAGResponse(
                query=sanitized_query,
                answer=clean_answer,
                status=status,
                is_grounded=is_grounded,
                sanitized_query=sanitized_query,
                citations=enriched_citations,
                graph_entities=[],
                guardrail_report=guardrail_report,
                faithfulness_score=gen_result.get("faithfulness_score", 1.0),
                answer_relevance_score=1.0 if is_grounded else 0.0,
                latency_breakdown=latencies,
                total_latency_ms=total_latency,
                generation_mode=gen_result.get("generation_mode", "grounded"),
                trace=RAGTrace(**trace_data)
            )

        finally:
            if should_close_db:
                db.close()

rag_pipeline = RAGPipeline()
