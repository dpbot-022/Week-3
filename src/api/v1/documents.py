import time
import uuid
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Document, ChunkRecord, User
from src.auth.deps import require_permission
from src.core.rbac import (
    PERM_READ_DOCUMENTS, PERM_UPLOAD_DOCUMENTS, PERM_DELETE_DOCUMENTS, PERM_MANAGE_DOCUMENTS, ALL_ROLES
)
from src.ingestion.parsers import DocumentParser
from src.ingestion.chunkers import get_chunker
from src.schemas.models import ChunkingStrategy, Chunk, IngestDocumentRequest, ChunkPreviewRequest
from src.embeddings.provider import embedding_provider
from src.vectorstore.chroma_store import vector_store
from src.retrieval.bm25_search import bm25_manager
from src.guardrails.pii_guard import pii_guard
from src.core.audit import audit_service
from src.core.metrics import metrics

router = APIRouter(prefix="/documents", tags=["Document Library"])

@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_READ_DOCUMENTS))
):
    """Lists only documents that the caller's role is allowed to access."""
    all_docs = db.query(Document).order_by(Document.created_at.desc()).all()
    accessible = [d for d in all_docs if current_user.role in d.allowed_roles]
    return [d.to_dict() for d in accessible]

@router.post("/upload")
async def upload_document(
    file: Optional[UploadFile] = File(None),
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    allowed_roles: Optional[str] = Form(None),
    effective_date: Optional[str] = Form(None),
    strategy: ChunkingStrategy = Form(ChunkingStrategy.RECURSIVE),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_UPLOAD_DOCUMENTS))
):
    """Uploads, extracts page numbers, redacts PII at ingestion, chunks, embeds, and updates Chroma & BM25."""
    start_time = time.time()
    raw_content = ""
    doc_title = title or "Untitled Document"
    filename = "document.txt"
    pages_data = []

    if file:
        filename = file.filename or "upload.pdf"
        file_bytes = await file.read()
        if not title:
            doc_title = filename

        if filename.lower().endswith(".pdf"):
            pages_data, meta = DocumentParser.parse_pdf(file_bytes, filename)
        else:
            text_str = file_bytes.decode("utf-8", errors="replace")
            cleaned, meta = DocumentParser.parse_text(text_str, filename)
            pages_data = [{"page_number": 1, "text": cleaned, "char_start": 0, "char_end": len(cleaned)}]
    elif content:
        cleaned, meta = DocumentParser.parse_text(content, filename)
        pages_data = [{"page_number": 1, "text": cleaned, "char_start": 0, "char_end": len(cleaned)}]
    else:
        raise HTTPException(status_code=400, detail="Must provide either a file or text content.")

    if not pages_data:
        raise HTTPException(status_code=400, detail="No readable content found in document.")

    # Parse allowed roles
    if allowed_roles:
        try:
            roles_list = json.loads(allowed_roles) if allowed_roles.startswith("[") else [r.strip() for r in allowed_roles.split(",")]
        except Exception:
            roles_list = ["viewer", "analyst", "compliance_manager", "auditor"]
    else:
        roles_list = ["viewer", "analyst", "compliance_manager", "auditor"]

    # Validate roles
    roles_list = [r for r in roles_list if r in ALL_ROLES]
    if not roles_list:
        roles_list = ["viewer", "analyst", "compliance_manager", "auditor"]

    doc_id = str(uuid.uuid4())
    chunker = get_chunker(strategy=strategy, chunk_size=400, chunk_overlap=40, embedding_provider=embedding_provider)

    total_chunks: List[Chunk] = []
    pii_counts: dict = {}

    for p in pages_data:
        page_num = p["page_number"]
        page_text = p["text"]

        # Step: Ingestion PII Redaction
        redacted_text, pii_entities = pii_guard.redact(page_text)
        for entity in pii_entities:
            etype = entity["entity_type"]
            pii_counts[etype] = pii_counts.get(etype, 0) + 1

        page_chunks = chunker.chunk(redacted_text, doc_id)
        for c in page_chunks:
            c.metadata["page_number"] = page_num
            c.metadata["title"] = doc_title
            c.metadata["allowed_roles"] = roles_list
            c.metadata["char_start"] = p["char_start"]
            c.metadata["char_end"] = p["char_end"]
            total_chunks.append(c)

    if not total_chunks:
        raise HTTPException(status_code=400, detail="Failed to produce chunks from document.")

    # 1. Embed and upsert into Chroma
    chunk_texts = [c.content for c in total_chunks]
    embeddings = embedding_provider.encode(chunk_texts).tolist()
    vector_store.add_chunks(chunks=total_chunks, embeddings=embeddings, allowed_roles=roles_list)

    # 2. Persist in SQLite
    doc_record = Document(
        id=doc_id,
        filename=filename,
        title=doc_title,
        allowed_roles_json=json.dumps(roles_list),
        chunk_count=len(total_chunks),
        effective_date=effective_date,
        pii_counts_json=json.dumps(pii_counts)
    )
    db.add(doc_record)

    for idx, c in enumerate(total_chunks):
        c_record = ChunkRecord(
            id=c.id,
            document_id=doc_id,
            chunk_index=idx,
            content=c.content,
            page_number=c.metadata.get("page_number", 1),
            char_start=c.metadata.get("char_start", 0),
            char_end=c.metadata.get("char_end", 0),
            allowed_roles_json=json.dumps(roles_list)
        )
        db.add(c_record)

    db.commit()
    db.refresh(doc_record)

    # 3. Synchronize per-role BM25 indices
    bm25_manager.rebuild_from_db(db)

    latency = round((time.time() - start_time) * 1000, 2)
    metrics.increment("documents_ingested")
    metrics.increment("chunks_indexed", len(total_chunks))

    audit_service.log(
        user_email=current_user.email,
        role=current_user.role,
        action="document:upload",
        resource=f"doc:{doc_id}:{doc_title}",
        details={"chunk_count": len(total_chunks), "allowed_roles": roles_list, "pii_counts": pii_counts},
        db=db
    )

    return {
        "document_id": doc_id,
        "title": doc_title,
        "filename": filename,
        "chunk_count": len(total_chunks),
        "allowed_roles": roles_list,
        "pii_counts": pii_counts,
        "latency_ms": latency
    }

@router.post("/preview-chunking")
def preview_chunking(
    payload: ChunkPreviewRequest,
    current_user: User = Depends(require_permission(PERM_READ_DOCUMENTS))
):
    chunker = get_chunker(strategy=payload.strategy, chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap, embedding_provider=embedding_provider)
    chunks = chunker.chunk(payload.text, "preview_doc")
    return {
        "chunk_count": len(chunks),
        "chunks": [c.dict() for c in chunks]
    }

@router.post("/reset")
def reset_database(current_user: User = Depends(require_permission(PERM_MANAGE_DOCUMENTS))):
    raise HTTPException(status_code=405, detail="Global Clear Database is disabled by policy. Use per-document delete.")

@router.post("/ingest")
def ingest_document(
    payload: IngestDocumentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_UPLOAD_DOCUMENTS))
):
    start_time = time.time()
    doc_id = str(uuid.uuid4())
    doc_title = payload.title or "Untitled Document"
    roles_list = payload.metadata.get("allowed_roles") or ["viewer", "analyst", "compliance_manager", "auditor"]
    roles_list = [r for r in roles_list if r in ALL_ROLES]
    if not roles_list:
        roles_list = ["viewer", "analyst", "compliance_manager", "auditor"]

    chunker = get_chunker(strategy=payload.strategy, chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap, embedding_provider=embedding_provider)

    redacted_text, pii_entities = pii_guard.redact(payload.content)
    pii_counts = {}
    for entity in pii_entities:
        etype = entity["entity_type"]
        pii_counts[etype] = pii_counts.get(etype, 0) + 1

    chunks = chunker.chunk(redacted_text, doc_id)
    for c in chunks:
        c.metadata["title"] = doc_title
        c.metadata["allowed_roles"] = roles_list
        c.metadata["page_number"] = payload.metadata.get("page_number", 1)

    chunk_texts = [c.content for c in chunks]
    if chunk_texts:
        embeddings = embedding_provider.encode(chunk_texts).tolist()
        vector_store.add_chunks(chunks=chunks, embeddings=embeddings, allowed_roles=roles_list)

    doc_record = Document(
        id=doc_id,
        filename=f"{doc_title}.txt",
        title=doc_title,
        allowed_roles_json=json.dumps(roles_list),
        chunk_count=len(chunks),
        pii_counts_json=json.dumps(pii_counts)
    )
    db.add(doc_record)
    for idx, c in enumerate(chunks):
        c_record = ChunkRecord(
            id=c.id,
            document_id=doc_id,
            chunk_index=idx,
            content=c.content,
            page_number=c.metadata.get("page_number", 1),
            char_start=0,
            char_end=len(c.content),
            allowed_roles_json=json.dumps(roles_list)
        )
        db.add(c_record)
    db.commit()
    db.refresh(doc_record)
    bm25_manager.rebuild_from_db(db)

    latency = round((time.time() - start_time) * 1000, 2)
    return {
        "document_id": doc_id,
        "title": doc_title,
        "strategy": payload.strategy,
        "chunk_count": len(chunks),
        "chunks": [c.dict() for c in chunks],
        "entities_extracted": len(pii_entities),
        "latency_ms": latency
    }

@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_DELETE_DOCUMENTS))
):
    """Deletes document from SQLite and ChromaDB, rebuilding per-role BM25."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc_title = doc.title
    # Delete from Chroma
    vector_store.delete_document(doc_id)

    # Delete from SQLite (cascades chunks)
    db.delete(doc)
    db.commit()

    # Rebuild per-role BM25
    bm25_manager.rebuild_from_db(db)

    audit_service.log(
        user_email=current_user.email,
        role=current_user.role,
        action="document:delete",
        resource=f"doc:{doc_id}:{doc_title}",
        db=db
    )

    return {"message": f"Document '{doc_title}' ({doc_id}) successfully deleted."}

@router.put("/{doc_id}/access")
def update_document_access(
    doc_id: str,
    allowed_roles: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_DOCUMENTS))
):
    """Updates allowed roles on document and chunks. Changes take effect immediately."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    clean_roles = [r for r in allowed_roles if r in ALL_ROLES]
    if not clean_roles:
        raise HTTPException(status_code=400, detail="Must specify at least one valid role.")

    doc.allowed_roles = clean_roles
    # Update chunk records
    for chunk in doc.chunks:
        chunk.allowed_roles = clean_roles

    db.commit()
    db.refresh(doc)

    # Re-index Chroma metadata for this document's chunks
    chunks_list = []
    embeddings_list = []
    for c in doc.chunks:
        ch = Chunk(
            id=c.id,
            document_id=doc.id,
            content=c.content,
            chunk_index=c.chunk_index,
            strategy=ChunkingStrategy.RECURSIVE,
            metadata={"page_number": c.page_number, "title": doc.title, "allowed_roles": clean_roles}
        )
        chunks_list.append(ch)
    if chunks_list:
        embeddings = embedding_provider.encode([c.content for c in chunks_list]).tolist()
        vector_store.add_chunks(chunks=chunks_list, embeddings=embeddings, allowed_roles=clean_roles)

    # Rebuild per-role BM25
    bm25_manager.rebuild_from_db(db)

    audit_service.log(
        user_email=current_user.email,
        role=current_user.role,
        action="document:access_update",
        resource=f"doc:{doc_id}:{doc.title}",
        details={"new_allowed_roles": clean_roles},
        db=db
    )

    return {"message": f"Updated access for '{doc.title}'", "allowed_roles": clean_roles}

@router.get("/{doc_id}/chunks")
def get_document_chunks(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_READ_DOCUMENTS))
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if current_user.role not in doc.allowed_roles:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this document.")

    chunks = db.query(ChunkRecord).filter(ChunkRecord.document_id == doc_id).order_by(ChunkRecord.chunk_index).all()
    return [{
        "id": c.id,
        "chunk_index": c.chunk_index,
        "content": c.content,
        "page_number": c.page_number,
        "char_start": c.char_start,
        "char_end": c.char_end
    } for c in chunks]
