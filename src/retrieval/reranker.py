from typing import List, Tuple
import threading
import numpy as np
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import ScoredChunk

class CrossEncoderReranker:
    """Neural cross-encoder reranker using ms-marco-MiniLM-L-6-v2."""
    def __init__(self, model_name: str = settings.RERANKER_MODEL):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(f"Loading CrossEncoder model: {self.model_name}")
                    from sentence_transformers import CrossEncoder
                    self._model = CrossEncoder(self.model_name)
                    logger.info("CrossEncoder model loaded successfully.")

    def rerank(self, query: str, candidates: List[ScoredChunk], top_k: int = 5) -> List[ScoredChunk]:
        if not candidates:
            return []
            
        self._load_model()
        pairs: List[Tuple[str, str]] = [(query, chunk.content) for chunk in candidates]
        
        raw_scores = self._model.predict(pairs, batch_size=32, show_progress_bar=False)
        
        # Apply sigmoid or min-max normalization to raw logits
        scores_arr = np.array(raw_scores, dtype=np.float32)
        exp_scores = 1.0 / (1.0 + np.exp(-scores_arr))  # Sigmoid transformation

        for i, chunk in enumerate(candidates):
            chunk.rerank_score = float(exp_scores[i])
            # Update final score to reflect cross-encoder relevance
            chunk.final_score = float(exp_scores[i])

        reranked = sorted(candidates, key=lambda c: c.final_score, reverse=True)
        return reranked[:top_k]

reranker = CrossEncoderReranker()
