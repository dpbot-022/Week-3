from typing import List, Dict, Any, Optional
from collections import defaultdict
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import ScoredChunk, SearchMode
from src.embeddings.provider import embedding_provider
from src.vectorstore.chroma_store import vector_store
from src.retrieval.bm25_search import bm25_manager
from src.retrieval.reranker import reranker
from src.retrieval.hyde import hyde_rewriter
from src.retrieval.deduplicator import deduplicator

class HybridSearchEngine:
    """Production hybrid search engine combining Dense (Vector) + Sparse (BM25) with RRF and Reranking."""
    def __init__(self, rrf_k: int = settings.RRF_K, alpha: float = settings.HYBRID_ALPHA):
        self.rrf_k = rrf_k
        self.alpha = alpha

    def search(
        self,
        query: str,
        top_k: int = 5,
        mode: SearchMode = SearchMode.HYBRID,
        use_reranker: bool = True,
        use_hyde: bool = False,
        role: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[ScoredChunk]:
        # Step 1: Query embedding (with optional HyDE)
        if use_hyde:
            query_emb = hyde_rewriter.get_hyde_embedding(query)
        else:
            query_emb = embedding_provider.encode(query).tolist()

        retrieval_limit = max(top_k * 3, settings.DEFAULT_RETRIEVAL_LIMIT)

        dense_results: List[ScoredChunk] = []
        sparse_results: List[ScoredChunk] = []

        # Step 2: Dense retrieval (pre-filtered strictly by role)
        if mode in (SearchMode.HYBRID, SearchMode.DENSE):
            dense_results = vector_store.query_dense(
                query_embedding=query_emb,
                top_k=retrieval_limit,
                role=role,
                filter_metadata=filter_metadata
            )

        # Step 3: Sparse retrieval (pre-filtered strictly by role index)
        if mode in (SearchMode.HYBRID, SearchMode.SPARSE):
            sparse_results = bm25_manager.search(
                query=query,
                top_k=retrieval_limit,
                role=role
            )

        # Step 4: Fusion
        if mode == SearchMode.DENSE:
            fused_candidates = dense_results
        elif mode == SearchMode.SPARSE:
            fused_candidates = sparse_results
        else:
            fused_candidates = self._reciprocal_rank_fusion(dense_results, sparse_results)

        # Step 5: Optional Cross-Encoder Neural Reranking
        if use_reranker and fused_candidates:
            rerank_pool = fused_candidates[:retrieval_limit]
            reranked_results = reranker.rerank(query=query, candidates=rerank_pool, top_k=retrieval_limit)
            fused_candidates = reranked_results

        # Step 6: Strict RBAC post-verification invariant check
        if role:
            verified_candidates = []
            for c in fused_candidates:
                allowed = c.metadata.get("allowed_roles", "")
                if isinstance(allowed, list):
                    roles_list = allowed
                elif isinstance(allowed, str):
                    roles_list = [r.strip() for r in allowed.split(",")]
                else:
                    roles_list = []
                
                # If chunk has role flags or allowed_roles list
                if role in roles_list or c.metadata.get(f"role_{role}", False):
                    verified_candidates.append(c)
                else:
                    logger.critical(f"LEAKAGE PREVENTED: Blocked chunk {c.id} missing role '{role}' from reaching context.")
            fused_candidates = verified_candidates

        # Step 7: Context Deduplication
        deduped = deduplicator.deduplicate(fused_candidates, max_chunks=top_k)
        return deduped

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[ScoredChunk],
        sparse_results: List[ScoredChunk]
    ) -> List[ScoredChunk]:
        """Calculates RRF score: sum(1 / (k + rank))."""
        rrf_scores: Dict[str, float] = defaultdict(float)
        chunk_map: Dict[str, ScoredChunk] = {}

        # Dense ranks
        for rank, chunk in enumerate(dense_results, start=1):
            chunk_map[chunk.id] = chunk
            rrf_scores[chunk.id] += 1.0 / (self.rrf_k + rank)

        # Sparse ranks
        for rank, chunk in enumerate(sparse_results, start=1):
            if chunk.id not in chunk_map:
                chunk_map[chunk.id] = chunk
            else:
                chunk_map[chunk.id].sparse_score = chunk.sparse_score
            rrf_scores[chunk.id] += 1.0 / (self.rrf_k + rank)

        # Build fused list
        fused: List[ScoredChunk] = []
        max_possible_rrf = 2.0 / (self.rrf_k + 1)
        for chunk_id, score in rrf_scores.items():
            chunk = chunk_map[chunk_id]
            chunk.rrf_score = score
            norm_score = round(min(1.0, score / max_possible_rrf), 4)
            chunk.final_score = norm_score
            fused.append(chunk)

        fused.sort(key=lambda c: c.final_score, reverse=True)
        return fused

hybrid_search = HybridSearchEngine()
