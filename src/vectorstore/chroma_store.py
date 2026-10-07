import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import Chunk, ScoredChunk

class ChromaVectorStore:
    """Production ChromaDB vector store repository."""
    def __init__(self, persist_dir: str = settings.CHROMA_PERSIST_DIR):
        self.persist_dir = persist_dir
        os.makedirs(self.persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_dir)

    def get_or_create_collection(self, collection_name: str = settings.DEFAULT_COLLECTION_NAME):
        try:
            return self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception:
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            return self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )

    def add_chunks(
        self,
        chunks: List[Chunk],
        embeddings: List[List[float]],
        collection_name: str = settings.DEFAULT_COLLECTION_NAME
    ):
        if not chunks:
            return
        collection = self.get_or_create_collection(collection_name)
        
        ids = [chunk.id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = []
        for chunk in chunks:
            meta = {
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "strategy": chunk.strategy.value,
                "character_count": chunk.character_count,
            }
            # Flatten any simple metadata
            for k, v in chunk.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[f"meta_{k}"] = v
            metadatas.append(meta)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Upserted {len(chunks)} chunks into Chroma collection '{collection_name}'")

    def query_dense(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        collection_name: str = settings.DEFAULT_COLLECTION_NAME
    ) -> List[ScoredChunk]:
        collection = self.get_or_create_collection(collection_name)
        
        count = collection.count()
        if count == 0:
            return []
            
        n_results = min(top_k, count)
        query_kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }
        if filter_metadata:
            query_kwargs["where"] = filter_metadata

        results = collection.query(**query_kwargs)

        scored_chunks: List[ScoredChunk] = []
        if not results or not results["ids"] or not results["ids"][0]:
            return scored_chunks

        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for i in range(len(ids)):
            # Convert cosine distance to cosine similarity (1 - dist)
            dist = distances[i] if distances else 0.0
            dense_sim = max(0.0, min(1.0, 1.0 - dist))
            doc_id = metas[i].get("document_id", "unknown") if metas and metas[i] else "unknown"

            scored_chunks.append(ScoredChunk(
                id=ids[i],
                document_id=doc_id,
                content=docs[i],
                metadata=metas[i] if metas else {},
                dense_score=dense_sim,
                final_score=dense_sim
            ))

        return scored_chunks

    def count(self, collection_name: str = settings.DEFAULT_COLLECTION_NAME) -> int:
        col = self.get_or_create_collection(collection_name)
        return col.count()

    def get_all_chunks(self, collection_name: str = settings.DEFAULT_COLLECTION_NAME) -> List[Dict[str, Any]]:
        col = self.get_or_create_collection(collection_name)
        total = col.count()
        if total == 0:
            return []
        data = col.get(include=["documents", "metadatas"])
        chunks = []
        for i in range(len(data["ids"])):
            chunks.append({
                "id": data["ids"][i],
                "content": data["documents"][i],
                "metadata": data["metadatas"][i]
            })
        return chunks

    def reset_collection(self, collection_name: str = settings.DEFAULT_COLLECTION_NAME):
        try:
            self.client.delete_collection(name=collection_name)
            logger.info(f"Deleted Chroma collection '{collection_name}'")
        except Exception as e:
            logger.warning(f"Collection reset warning: {e}")
        self.get_or_create_collection(collection_name)

vector_store = ChromaVectorStore()
