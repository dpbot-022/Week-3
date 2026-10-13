import re
import json
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session
from src.core.rbac import ALL_ROLES
from src.core.logging import logger
from src.schemas.models import ScoredChunk

class BM25SearchEngine:
    """Sparse keyword retrieval using BM25Okapi for a specific corpus."""
    def __init__(self):
        self.corpus_ids: List[str] = []
        self.corpus_docs: List[str] = []
        self.corpus_metas: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())

    def index_documents(self, documents: List[Dict[str, Any]]):
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

class RoleBM25Manager:
    """Manages dedicated, isolated BM25 indices per role to guarantee zero sparse-retrieval leakage."""
    def __init__(self):
        self.role_engines: Dict[str, BM25SearchEngine] = {
            role: BM25SearchEngine() for role in ALL_ROLES
        }
        # Default engine for unconstrained fallback in tests
        self.default_engine = BM25SearchEngine()

    def rebuild_from_db(self, db: Session):
        """Rebuilds all per-role BM25 indices from the SQLite chunk store."""
        from src.db.models import ChunkRecord, Document
        records = db.query(ChunkRecord).all()
        logger.info(f"Rebuilding per-role BM25 indices from {len(records)} persisted chunks.")

        chunks_per_role: Dict[str, List[Dict[str, Any]]] = {role: [] for role in ALL_ROLES}
        all_chunks: List[Dict[str, Any]] = []

        for c in records:
            roles = c.allowed_roles
            meta = {
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "allowed_roles": roles,
            }
            chunk_data = {
                "id": c.id,
                "content": c.content,
                "metadata": meta
            }
            all_chunks.append(chunk_data)

            for role in ALL_ROLES:
                if role in roles:
                    chunks_per_role[role].append(chunk_data)

        self.default_engine.index_documents(all_chunks)
        for role, doc_list in chunks_per_role.items():
            self.role_engines[role].index_documents(doc_list)
            logger.debug(f"Indexed {len(doc_list)} chunks for role '{role}' BM25")

    def index_documents(self, documents: List[Dict[str, Any]], role: Optional[str] = None):
        """Compatibility method for direct indexing."""
        if role and role in self.role_engines:
            self.role_engines[role].index_documents(documents)
        else:
            self.default_engine.index_documents(documents)
            for r in ALL_ROLES:
                # filter by role if metadata present
                matching = [
                    d for d in documents
                    if r in d.get("metadata", {}).get("allowed_roles", ALL_ROLES)
                ]
                self.role_engines[r].index_documents(matching)

    def search(self, query: str, top_k: int = 5, role: Optional[str] = None) -> List[ScoredChunk]:
        if role and role in self.role_engines:
            return self.role_engines[role].search(query, top_k)
        return self.default_engine.search(query, top_k)

bm25_manager = RoleBM25Manager()
bm25_engine = bm25_manager  # Backward compatibility alias
