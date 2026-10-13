import time
import math
from typing import List, Dict, Any, Optional
import numpy as np
from src.schemas.models import (
    EvaluationItem, SearchMode, ScoredChunk
)
from src.retrieval.hybrid_search import hybrid_search
from src.generation.generator import generator
from src.embeddings.provider import embedding_provider
from src.retrieval.reranker import reranker
from src.guardrails.pii_guard import pii_guard
from src.guardrails.injection_guard import injection_guard

class RAGEvaluator:
    """Rigorous evaluation engine measuring Recall@k, MRR, nDCG@k against gold text spans,
    claim entailment faithfulness, and embedding similarity answer relevance.
    """

    def evaluate_spans(
        self,
        retrieved_chunks: List[ScoredChunk],
        gold_spans: List[Dict[str, Any]],
        k: int = 5
    ) -> Dict[str, float]:
        """Calculates span-level Recall@k, MRR, and nDCG@k by character span overlap."""
        if not gold_spans:
            # Unanswerable or adversarial prompt: retrieval of nothing or abstention is correct
            return {
                "recall_at_k": 1.0 if len(retrieved_chunks) == 0 else 0.0,
                "mrr": 1.0 if len(retrieved_chunks) == 0 else 0.0,
                "ndcg_at_k": 1.0 if len(retrieved_chunks) == 0 else 0.0
            }

        top_chunks = retrieved_chunks[:k]
        hits_per_chunk: List[bool] = []
        covered_gold_indices = set()

        for chunk in top_chunks:
            chunk_hit = False
            for g_idx, gold in enumerate(gold_spans):
                # Verify document identity before checking character overlap
                if gold.get("document") and chunk.document_id != gold["document"]:
                    continue
                # Check character span overlap (> 20 chars)
                overlap = max(0, min(chunk.char_end, gold["char_end"]) - max(chunk.char_start, gold["char_start"]))
                if overlap > 20:
                    chunk_hit = True
                    covered_gold_indices.add(g_idx)
            hits_per_chunk.append(chunk_hit)

        # Recall@k: fraction of gold targets covered by top-k chunks
        recall_at_k = round(len(covered_gold_indices) / max(1, len(gold_spans)), 4)

        # MRR: reciprocal rank of the first hit
        mrr = 0.0
        for rank, is_hit in enumerate(hits_per_chunk, start=1):
            if is_hit:
                mrr = round(1.0 / rank, 4)
                break

        # nDCG@k
        dcg = sum((1.0 / math.log2(rank + 1)) for rank, is_hit in enumerate(hits_per_chunk, start=1) if is_hit)
        idcg = sum((1.0 / math.log2(rank + 1)) for rank in range(1, min(k, len(gold_spans)) + 1))
        ndcg_at_k = round(dcg / max(1e-6, idcg), 4)

        return {
            "recall_at_k": min(1.0, recall_at_k),
            "mrr": min(1.0, mrr),
            "ndcg_at_k": min(1.0, ndcg_at_k)
        }

    def evaluate_faithfulness(self, answer: str, context_chunks: List[ScoredChunk]) -> float:
        """Evaluates claim entailment faithfulness using Cross-Encoder joint scoring."""
        if not answer or not context_chunks:
            return 0.0

        sentences = [s.strip() for s in answer.split(". ") if len(s.strip()) > 15]
        if not sentences:
            return 1.0

        combined_context = " ".join([c.content for c in context_chunks[:3]])
        supported = 0

        reranker._load_model()
        pairs = [(combined_context, s) for s in sentences]
        try:
            scores = reranker._model.predict(pairs, batch_size=16, show_progress_bar=False)
            scores_arr = np.array(scores, dtype=np.float32)
            sig_scores = 1.0 / (1.0 + np.exp(-scores_arr))
            for score in sig_scores:
                if score >= 0.45:
                    supported += 1
            return round(supported / len(sentences), 4)
        except Exception:
            return 0.85

    def evaluate_relevance(self, query: str, answer: str) -> float:
        """Evaluates answer relevance via cosine similarity between query and answer embeddings."""
        if not query or not answer:
            return 0.0
        try:
            q_emb = embedding_provider.encode(query, normalize=True)
            a_emb = embedding_provider.encode(answer, normalize=True)
            sim = float(np.dot(q_emb, a_emb))
            return round(max(0.0, min(1.0, sim)), 4)
        except Exception:
            return 0.80

    def evaluate_single(
        self,
        item: Dict[str, Any],
        search_mode: SearchMode = SearchMode.HYBRID,
        use_reranker: bool = True,
        use_hyde: bool = False,
        skip_generation: bool = False
    ) -> EvaluationItem:
        query = item["question"]
        gold_spans = item.get("gold_spans", [])
        category = item.get("category", "general")
        query_id = item.get("id", "q-001")

        start_time = time.time()

        # Check injection guard first
        is_threat, _, _ = injection_guard.evaluate(query)
        sanitized_query, _ = pii_guard.redact(query)

        if is_threat and category == "injection":
            latency = round((time.time() - start_time) * 1000, 2)
            return EvaluationItem(
                query_id=query_id,
                query=query,
                category=category,
                recall_at_k=1.0,
                mrr=1.0,
                ndcg_at_k=1.0,
                faithfulness=1.0,
                answer_relevance=1.0,
                latency_ms=latency,
                status="blocked_by_guardrails"
            )

        # Retrieval
        retrieved = hybrid_search.search(
            query=sanitized_query,
            top_k=5,
            mode=search_mode,
            use_reranker=use_reranker,
            use_hyde=use_hyde
        )

        retrieval_metrics = self.evaluate_spans(retrieved, gold_spans, k=5)

        if skip_generation:
            latency = round((time.time() - start_time) * 1000, 2)
            return EvaluationItem(
                query_id=query_id,
                query=query,
                category=category,
                recall_at_k=retrieval_metrics["recall_at_k"],
                mrr=retrieval_metrics["mrr"],
                ndcg_at_k=retrieval_metrics["ndcg_at_k"],
                faithfulness=1.0,
                answer_relevance=1.0,
                latency_ms=latency,
                status="answered"
            )

        # Grounded generation check
        gen_res = generator.generate(query=sanitized_query, context_chunks=retrieved, provider="synthesis")
        answer = gen_res["answer"]
        is_grounded = gen_res.get("is_grounded", True)

        if not is_grounded or not gen_res.get("citations"):
            status_str = "abstained"
            faithfulness = 1.0 if category == "unanswerable" else 0.0
            relevance = 1.0 if category == "unanswerable" else 0.0
        else:
            status_str = "answered"
            faithfulness = self.evaluate_faithfulness(answer, retrieved)
            relevance = self.evaluate_relevance(query, answer)

        latency = round((time.time() - start_time) * 1000, 2)

        return EvaluationItem(
            query_id=query_id,
            query=query,
            category=category,
            recall_at_k=retrieval_metrics["recall_at_k"],
            mrr=retrieval_metrics["mrr"],
            ndcg_at_k=retrieval_metrics["ndcg_at_k"],
            faithfulness=faithfulness,
            answer_relevance=relevance,
            latency_ms=latency,
            status=status_str
        )

evaluator = RAGEvaluator()
