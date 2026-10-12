import re
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from src.schemas.models import ScoredChunk

class BM25SearchEngine:
    """Sparse keyword retrieval using BM25Okapi with tokenization and corpus indexing."""
    def __init__(self):
        self.corpus_ids: List[str] = []
        self.corpus_docs: List[str] = []
        self.corpus_metas: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None

    def _tokenize(self, text: str) -> List[str]:
        # Lowercase and split on non-alphanumeric tokens
        tokens = re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())
        return tokens

    def index_documents(self, documents: List[Dict[str, Any]]):
        """Index chunks: dicts with 'id', 'content', 'metadata'."""
        self.corpus_ids = []
        self.corpus_docs = []
        self.corpus_metas = []
        self.tokenized_corpus = []

        for doc in documents:
            self.corpus_ids.append(doc["id"])
            self.corpus_docs.append(doc["content"])
            self.corpus_metas.append(doc.get("metadata", {}))
            tokens = self._tokenize(doc["content"])
            self.tokenized_corpus.append(tokens)

        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self.bm25 = None

    def search(self, query: str, top_k: int = 5) -> List[ScoredChunk]:
        if not self.bm25 or not self.corpus_docs:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        raw_scores = self.bm25.get_scores(query_tokens)
        max_score = max(raw_scores) if len(raw_scores) > 0 and max(raw_scores) > 0 else 1.0

        # Rank indices
        ranked_indices = sorted(range(len(raw_scores)), key=lambda i: raw_scores[i], reverse=True)
        top_indices = [idx for idx in ranked_indices[:top_k] if raw_scores[idx] > 0]

        scored_chunks: List[ScoredChunk] = []
        for idx in top_indices:
            normalized_score = float(raw_scores[idx] / max_score)
            meta = self.corpus_metas[idx]
            doc_id = meta.get("document_id", "unknown")
            c_start = int(meta.get("start_char", meta.get("char_start", 0)))
            c_end = int(meta.get("end_char", meta.get("char_end", 0)))
            scored_chunks.append(ScoredChunk(
                id=self.corpus_ids[idx],
                document_id=doc_id,
                content=self.corpus_docs[idx],
                metadata=meta,
                sparse_score=normalized_score,
                final_score=normalized_score,
                char_start=c_start,
                char_end=c_end
            ))

        return scored_chunks

bm25_engine = BM25SearchEngine()
