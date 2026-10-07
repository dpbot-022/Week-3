import time
from typing import List, Dict, Any, Optional
from src.schemas.models import (
    EvaluationItem, BenchmarkReport, SearchMode, RAGRequest
)
from src.retrieval.hybrid_search import hybrid_search
from src.guardrails.output_guard import output_guard
from src.generation.generator import generator

class RAGEvaluator:
    """Evaluates RAG pipeline components along the RAG Triad: Context Precision, Faithfulness, and Answer Relevance."""

    def evaluate_retrieval(
        self,
        query: str,
        retrieved_contexts: List[str],
        expected_keywords: List[str]
    ) -> Dict[str, float]:
        if not retrieved_contexts or not expected_keywords:
            return {"context_precision": 0.0, "context_recall": 0.0}

        hits = 0
        joined_contexts = " ".join(retrieved_contexts).lower()
        for kw in expected_keywords:
            if kw.lower() in joined_contexts:
                hits += 1

        recall = round(hits / len(expected_keywords), 2)
        precision = round(min(1.0, hits / max(1, len(retrieved_contexts))), 2)

        return {
            "context_precision": precision,
            "context_recall": recall
        }

    def evaluate_single(
        self,
        query: str,
        expected_keywords: Optional[List[str]] = None,
        search_mode: SearchMode = SearchMode.HYBRID,
        use_reranker: bool = True
    ) -> EvaluationItem:
        start_time = time.time()
        
        # Retrieval
        retrieved = hybrid_search.search(
            query=query,
            top_k=5,
            mode=search_mode,
            use_reranker=use_reranker
        )
        context_texts = [c.content for c in retrieved]

        # Generation
        gen_res = generator.generate(query=query, context_chunks=retrieved)
        answer = gen_res["answer"]

        # Faithfulness
        faithfulness, _ = output_guard.check_faithfulness(answer, context_texts)

        # Retrieval Precision & Recall
        kws = expected_keywords or query.lower().split()
        retrieval_metrics = self.evaluate_retrieval(query, context_texts, kws)

        # Answer Relevance
        q_tokens = set(query.lower().split())
        a_tokens = set(answer.lower().split())
        overlap = len(q_tokens & a_tokens)
        ans_relevance = round(min(1.0, overlap / max(1, len(q_tokens) * 0.7)), 2)

        latency = round((time.time() - start_time) * 1000, 2)

        mode_name = f"{search_mode.value}{'+reranker' if use_reranker else ''}"

        return EvaluationItem(
            query=query,
            ground_truth=None,
            context_precision=retrieval_metrics["context_precision"],
            context_recall=retrieval_metrics["context_recall"],
            faithfulness=faithfulness,
            answer_relevance=ans_relevance,
            latency_ms=latency,
            retrieval_mode=mode_name
        )

evaluator = RAGEvaluator()
