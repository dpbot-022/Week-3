from typing import List, Union
import numpy as np
import threading
from src.core.config import settings
from src.core.logging import logger

class EmbeddingProvider:
    """Production provider for local Hugging Face Sentence Transformers."""
    def __init__(self, model_name: str = settings.EMBEDDING_MODEL):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self._cache = {}

    def _load_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(f"Loading SentenceTransformer model: {self.model_name}")
                    from sentence_transformers import SentenceTransformer
                    self._model = SentenceTransformer(self.model_name)
                    logger.info("SentenceTransformer model loaded successfully.")

    def encode(self, texts: Union[str, List[str]], normalize: bool = True) -> np.ndarray:
        self._load_model()
        is_single = isinstance(texts, str)
        text_list = [texts] if is_single else texts
        
        # Check cache for single text
        if is_single and texts in self._cache:
            return self._cache[texts]

        embeddings = self._model.encode(
            text_list,
            normalize_embeddings=normalize,
            batch_size=32,
            show_progress_bar=False
        )
        
        embeddings_np = np.array(embeddings, dtype=np.float32)

        if is_single:
            self._cache[texts] = embeddings_np[0]
            return embeddings_np[0]
            
        return embeddings_np

    def dimension(self) -> int:
        return settings.EMBEDDING_DIMENSION

embedding_provider = EmbeddingProvider()
