import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from src.db.session import init_db, SessionLocal
from src.db.models import Document, ChunkRecord, User
from src.core.rbac import ALL_ROLES
from src.ingestion.parsers import DocumentParser
from src.ingestion.chunkers import get_chunker
from src.schemas.models import ChunkingStrategy, Chunk
from src.embeddings.provider import embedding_provider
from src.vectorstore.chroma_store import vector_store
from src.retrieval.bm25_search import bm25_manager
from src.guardrails.pii_guard import pii_guard
from src.core.logging import logger

def seed_users(db: Session):
    """Ensure standard demo users exist for each role."""
    roles = ["admin", "compliance_manager", "analyst", "viewer", "auditor"]
    for role in roles:
        email = f"{role}@safestrata.local"
        existing = db.query(User).filter(User.email == email).first()
        if not existing:
            user = User(
                email=email,
                role=role,
                role_version=1,
                is_active=True
            )
            db.add(user)
    db.commit()
    logger.info("Default role users verified in database.")

def seed_corpus():
    start_time = time.time()
    init_db()
    
    corpus_dir = Path("/Users/bot/Desktop/safestrata/data/corpus")
    manifest_file = corpus_dir / "corpus_manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"Manifest file not found at {manifest_file}. Run scripts/prepare_corpus.py first.")

    manifest = json.loads(manifest_file.read_text())
    logger.info(f"Loaded manifest with {len(manifest)} documents.")

    with SessionLocal() as db:
        seed_users(db)
        
        # Reset previous corpus docs if present to ensure clean idempotent seed
        existing_doc_ids = [m["id"] for m in manifest]
        for doc_id in existing_doc_ids:
            old_doc = db.query(Document).filter(Document.id == doc_id).first()
            if old_doc:
                vector_store.delete_document(doc_id)
                db.delete(old_doc)
        db.commit()

        chunker = get_chunker(strategy=ChunkingStrategy.RECURSIVE, chunk_size=400, chunk_overlap=40, embedding_provider=embedding_provider)
        total_ingested_chunks = 0
        total_ingested_pages = 0

        print("\n" + "=" * 95)
        print(f"{'DOCUMENT SEED SUMMARY':^95}")
        print("=" * 95)
        print(f"{'Title':<45} | {'Pages':<6} | {'Chunks':<7} | {'Allowed Roles':<25}")
        print("-" * 95)

        for entry in manifest:
            doc_id = entry["id"]
            filename = entry["filename"]
            title = entry["title"]
            allowed_roles = entry["allowed_roles"]
            effective_date = entry.get("effective_date")
            file_path = corpus_dir / filename

            if not file_path.exists():
                logger.error(f"File {file_path} does not exist, skipping.")
                continue

            file_bytes = file_path.read_bytes()
            pages_data, _ = DocumentParser.parse_pdf(file_bytes, filename)
            doc_pages = len(pages_data)
            total_ingested_pages += doc_pages

            doc_chunks: list[Chunk] = []
            pii_counts: dict[str, int] = {}

            for p in pages_data:
                page_num = p["page_number"]
                page_text = p["text"]

                # Ingestion PII redaction
                redacted_text, pii_entities = pii_guard.redact(page_text)
                for ent in pii_entities:
                    etype = ent["entity_type"]
                    pii_counts[etype] = pii_counts.get(etype, 0) + 1

                page_chunks = chunker.chunk(redacted_text, doc_id)
                for c in page_chunks:
                    c.metadata["page_number"] = page_num
                    c.metadata["title"] = title
                    c.metadata["allowed_roles"] = allowed_roles
                    c.metadata["char_start"] = p["char_start"]
                    c.metadata["char_end"] = p["char_end"]
                    doc_chunks.append(c)

            if doc_chunks:
                # 1. Embed and upsert into Chroma
                chunk_texts = [c.content for c in doc_chunks]
                embeddings = embedding_provider.encode(chunk_texts).tolist()
                vector_store.add_chunks(chunks=doc_chunks, embeddings=embeddings, allowed_roles=allowed_roles)

                # 2. Persist in SQLite
                doc_record = Document(
                    id=doc_id,
                    filename=filename,
                    title=title,
                    allowed_roles_json=json.dumps(allowed_roles),
                    chunk_count=len(doc_chunks),
                    effective_date=effective_date,
                    pii_counts_json=json.dumps(pii_counts)
                )
                db.add(doc_record)

                for idx, c in enumerate(doc_chunks):
                    c_record = ChunkRecord(
                        id=c.id,
                        document_id=doc_id,
                        chunk_index=idx,
                        content=c.content,
                        page_number=c.metadata.get("page_number", 1),
                        char_start=c.metadata.get("char_start", 0),
                        char_end=c.metadata.get("char_end", 0),
                        allowed_roles_json=json.dumps(allowed_roles)
                    )
                    db.add(c_record)

                db.commit()
                total_ingested_chunks += len(doc_chunks)

            roles_str = ",".join(allowed_roles)
            if len(roles_str) > 24:
                roles_str = roles_str[:21] + "..."
            print(f"{title[:44]:<45} | {doc_pages:<6} | {len(doc_chunks):<7} | {roles_str:<25}")

        # 3. Synchronize per-role BM25 indices
        print("-" * 95)
        bm25_manager.rebuild_from_db(db)
        duration = round(time.time() - start_time, 2)
        print(f"Total: {total_ingested_pages} pages, {total_ingested_chunks} chunks ingested across {len(manifest)} documents in {duration}s.")
        print("=" * 95 + "\n")

if __name__ == "__main__":
    seed_corpus()
