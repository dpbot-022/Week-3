import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import Chunk, ScoredChunk
from src.core.rbac import ALL_ROLES

class ChromaVectorStore:
    """Production ChromaDB vector store repository with metadata role filtering."""
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
        allowed_roles: Optional[List[str]] = None,
        collection_name: str = settings.DEFAULT_COLLECTION_NAME
    ):
        if not chunks:
            return
        collection = self.get_or_create_collection(collection_name)
        
        ids = [chunk.id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = []
        for chunk in chunks:
            roles = chunk.metadata.get("allowed_roles") or allowed_roles or ["viewer", "analyst", "compliance_manager", "auditor"]
            if isinstance(roles, str):
                roles = [r.strip() for r in roles.split(",")]

            meta = {
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "strategy": chunk.strategy.value if hasattr(chunk.strategy, "value") else str(chunk.strategy),
                "character_count": chunk.character_count,
                "page_number": int(chunk.metadata.get("page_number", 1)),
                "title": str(chunk.metadata.get("title", "Document")),
                "allowed_roles": ",".join(roles),
            }
            # Add explicit role boolean flags for indexed Chroma filtering
            for r in ALL_ROLES:
                meta[f"role_{r}"] = (r in roles)

            # Flatten additional simple metadata
            for k, v in chunk.metadata.items():
                if k not in meta and isinstance(v, (str, int, float, bool)):
                    meta[f"meta_{k}"] = v
            metadatas.append(meta)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Upserted {len(chunks)} chunks into Chroma collection '{collection_name}' with RBAC tags")

    def query_dense(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        role: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        collection_name: str = settings.DEFAULT_COLLECTION_NAME
    ) -> List[ScoredChunk]:
        collection = self.get_or_create_collection(collection_name)
        
        count = collection.count()
        if count == 0:
            return []
            
        n_results = min(top_k * 3, count)  # fetch sufficient candidates
        query_kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }

        # Build where filter with role constraints
        where_conditions = []
        if role:
            where_conditions.append({f"role_{role}": True})
        if filter_metadata:
            where_conditions.append(filter_metadata)

        if len(where_conditions) == 1:
            query_kwargs["where"] = where_conditions[0]
        elif len(where_conditions) > 1:
            query_kwargs["where"] = {"$and": where_conditions}

        try:
            results = collection.query(**query_kwargs)
        except Exception as e:
            logger.warning(f"Chroma query error with filter: {e}. Falling back to clean query.")
            del query_kwargs["where"]
            results = collection.query(**query_kwargs)

        scored_chunks: List[ScoredChunk] = []
        if not results or not results["ids"] or not results["ids"][0]:
            return scored_chunks

        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for i in range(len(ids)):
            meta = metas[i] if metas else {}
            # Double-check role security gate in case backend where-filter was bypassed
            if role:
                if not meta.get(f"role_{role}", False):
                    continue

            dist = distances[i] if distances else 0.0
            dense_sim = max(0.0, min(1.0, 1.0 - dist))
            doc_id = meta.get("document_id", "unknown")

            scored_chunks.append(ScoredChunk(
                id=ids[i],
                document_id=doc_id,
                content=docs[i],
                metadata=meta,
                dense_score=dense_sim,
                final_score=dense_sim
            ))

        return scored_chunks[:top_k]

    def delete_document(self, document_id: str, collection_name: str = settings.DEFAULT_COLLECTION_NAME):
        """Per-document deletion adhering to zero global clear rule."""
        col = self.get_or_create_collection(collection_name)
        try:
            col.delete(where={"document_id": document_id})
            logger.info(f"Deleted chunks for document '{document_id}' from Chroma collection '{collection_name}'")
        except Exception as e:
            logger.error(f"Failed to delete document '{document_id}' from Chroma: {e}")

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

vector_store = ChromaVectorStore()
