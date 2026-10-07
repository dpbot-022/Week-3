import re
import uuid
from typing import List, Dict, Any, Optional
import numpy as np
from src.schemas.models import Chunk, ChunkingStrategy

class BaseChunker:
    """Base class for all document chunking strategies."""
    def chunk(self, text: str, document_id: str, **kwargs) -> List[Chunk]:
        raise NotImplementedError

class CharacterChunker(BaseChunker):
    """Level 1: Fixed character length splitter with overlap."""
    def __init__(self, chunk_size: int = 350, chunk_overlap: int = 35):
        self.chunk_size = max(10, chunk_size)
        self.chunk_overlap = min(chunk_overlap, self.chunk_size - 1)

    def chunk(self, text: str, document_id: str, **kwargs) -> List[Chunk]:
        if not text:
            return []
        chunks = []
        start = 0
        text_len = len(text)
        idx = 0
        step = self.chunk_size - self.chunk_overlap
        
        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            content = text[start:end]
            if content.strip():
                chunks.append(Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    content=content,
                    chunk_index=idx,
                    strategy=ChunkingStrategy.CHARACTER,
                    character_count=len(content),
                    token_estimate=max(1, len(content) // 4),
                    metadata={"start_char": start, "end_char": end}
                ))
                idx += 1
            start += step
            if start + self.chunk_overlap >= text_len and start < text_len:
                break
        return chunks

class RecursiveCharacterChunker(BaseChunker):
    """Level 2: Hierarchical separator splitter (\n\n, \n, sentence end, space, char)."""
    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 40, separators: Optional[List[str]] = None):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

    def chunk(self, text: str, document_id: str, **kwargs) -> List[Chunk]:
        if not text:
            return []
        raw_chunks = self._split_text(text, self.separators)
        chunks = []
        for idx, content in enumerate(raw_chunks):
            if content.strip():
                chunks.append(Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    content=content.strip(),
                    chunk_index=idx,
                    strategy=ChunkingStrategy.RECURSIVE,
                    character_count=len(content.strip()),
                    token_estimate=max(1, len(content.strip()) // 4),
                    metadata={"separator_level": "hierarchical"}
                ))
        return chunks

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break

        splits = text.split(separator) if separator else list(text)
        good_splits: List[str] = []

        for s in splits:
            if len(s) < self.chunk_size:
                good_splits.append(s)
            else:
                if good_splits:
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    good_splits = []
                if not new_separators:
                    final_chunks.append(s[:self.chunk_size])
                else:
                    other_chunks = self._split_text(s, new_separators)
                    final_chunks.extend(other_chunks)

        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)

        return final_chunks

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        docs: List[str] = []
        current_doc: List[str] = []
        total_len = 0

        for s in splits:
            length = len(s)
            if total_len + length + (len(separator) if current_doc else 0) > self.chunk_size:
                if current_doc:
                    doc = separator.join(current_doc)
                    if doc.strip():
                        docs.append(doc)
                    while total_len > self.chunk_overlap and current_doc:
                        popped = current_doc.pop(0)
                        total_len -= len(popped) + (len(separator) if current_doc else 0)
                current_doc.append(s)
                total_len += length
            else:
                current_doc.append(s)
                total_len += length + (len(separator) if len(current_doc) > 1 else 0)

        if current_doc:
            doc = separator.join(current_doc)
            if doc.strip():
                docs.append(doc)
        return docs

class DocumentSpecificChunker(BaseChunker):
    """Level 3: Structure-aware chunker for Markdown headers, code blocks, and tables."""
    def __init__(self, chunk_size: int = 500):
        self.chunk_size = chunk_size

    def chunk(self, text: str, document_id: str, **kwargs) -> List[Chunk]:
        if not text:
            return []
        
        # Split on Markdown headers (# Header, ## Header, etc.)
        header_pattern = r"(?=(?:^|\n)#{1,6}\s+)"
        sections = re.split(header_pattern, text)
        sections = [s for s in sections if s.strip()]

        if len(sections) <= 1:
            # Fall back to code block or table detection
            block_pattern = r"(?=(?:^|\n)(?:```|\|))"
            sections = re.split(block_pattern, text)
            sections = [s for s in sections if s.strip()]

        chunks = []
        idx = 0
        for section in sections:
            section = section.strip()
            # If a section is too large, recursively split it
            if len(section) > self.chunk_size:
                sub_chunker = RecursiveCharacterChunker(chunk_size=self.chunk_size, chunk_overlap=40)
                sub_chunks = sub_chunker.chunk(section, document_id)
                for sc in sub_chunks:
                    sc.chunk_index = idx
                    sc.strategy = ChunkingStrategy.DOCUMENT_SPECIFIC
                    sc.metadata["structure_type"] = "sub_section"
                    chunks.append(sc)
                    idx += 1
            else:
                chunks.append(Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    content=section,
                    chunk_index=idx,
                    strategy=ChunkingStrategy.DOCUMENT_SPECIFIC,
                    character_count=len(section),
                    token_estimate=max(1, len(section) // 4),
                    metadata={"structure_type": "header_or_block"}
                ))
                idx += 1
        return chunks

class SemanticChunker(BaseChunker):
    """Level 4: Semantic breakpoint splitting using sentence embeddings & distance percentiles."""
    def __init__(self, embedding_provider=None, buffer_size: int = 1, breakpoint_percentile: float = 90.0):
        self.embedding_provider = embedding_provider
        self.buffer_size = buffer_size
        self.breakpoint_percentile = breakpoint_percentile

    def chunk(self, text: str, document_id: str, **kwargs) -> List[Chunk]:
        if not text:
            return []
        
        # Split into sentences
        sentences = re.split(r"(?<=[.?!])\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= 3:
            return [Chunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                content=text.strip(),
                chunk_index=0,
                strategy=ChunkingStrategy.SEMANTIC,
                character_count=len(text.strip()),
                token_estimate=max(1, len(text.strip()) // 4),
                metadata={"breakpoint_count": 0}
            )]

        # Group sentences with surrounding context buffer
        combined_groups = []
        for i in range(len(sentences)):
            start_i = max(0, i - self.buffer_size)
            end_i = min(len(sentences), i + self.buffer_size + 1)
            combined_groups.append(" ".join(sentences[start_i:end_i]))

        # Calculate embeddings
        if self.embedding_provider:
            embeddings = self.embedding_provider.encode(combined_groups)
        else:
            # Fallback simple embedding if provider not injected
            embeddings = np.array([self._fallback_embed(g) for g in combined_groups])

        # Calculate cosine distances between consecutive groups
        distances = []
        for i in range(len(embeddings) - 1):
            vec1 = embeddings[i]
            vec2 = embeddings[i + 1]
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 > 0 and norm2 > 0:
                similarity = np.dot(vec1, vec2) / (norm1 * norm2)
                distance = 1.0 - max(-1.0, min(1.0, similarity))
            else:
                distance = 0.0
            distances.append(distance)

        if not distances:
            threshold = 0.5
        else:
            threshold = float(np.percentile(distances, self.breakpoint_percentile))

        # Break into chunks at distance outliers
        chunks = []
        current_chunk_sentences = [sentences[0]]
        chunk_idx = 0

        for i, dist in enumerate(distances):
            if dist > threshold:
                # Breakpoint triggered
                chunk_text = " ".join(current_chunk_sentences).strip()
                if chunk_text:
                    chunks.append(Chunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        content=chunk_text,
                        chunk_index=chunk_idx,
                        strategy=ChunkingStrategy.SEMANTIC,
                        character_count=len(chunk_text),
                        token_estimate=max(1, len(chunk_text) // 4),
                        metadata={"split_distance": float(dist), "threshold": threshold}
                    ))
                    chunk_idx += 1
                current_chunk_sentences = [sentences[i + 1]]
            else:
                current_chunk_sentences.append(sentences[i + 1])

        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences).strip()
            if chunk_text:
                chunks.append(Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    content=chunk_text,
                    chunk_index=chunk_idx,
                    strategy=ChunkingStrategy.SEMANTIC,
                    character_count=len(chunk_text),
                    token_estimate=max(1, len(chunk_text) // 4),
                    metadata={"split_distance": 0.0, "threshold": threshold}
                ))

        return chunks

    def _fallback_embed(self, text: str, dim: int = 128) -> np.ndarray:
        vec = np.zeros(dim, dtype=np.float32)
        for word in text.lower().split():
            h = hash(word) % dim
            vec[h] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

class AgenticPropositionChunker(BaseChunker):
    """Level 5: Propositional extraction and thematic clustering."""
    def __init__(self, max_propositions_per_chunk: int = 4):
        self.max_propositions_per_chunk = max_propositions_per_chunk

    def chunk(self, text: str, document_id: str, **kwargs) -> List[Chunk]:
        if not text:
            return []
        
        # Extract atomic proposition statements
        propositions = self._extract_propositions(text)
        if not propositions:
            propositions = [text]

        clusters: List[Dict[str, Any]] = []
        for prop in propositions:
            assigned = False
            for cluster in clusters:
                if len(cluster["propositions"]) < self.max_propositions_per_chunk:
                    # Check semantic overlap using keyword jaccard
                    overlap = self._compute_thematic_overlap(prop, cluster["summary"])
                    if overlap > 0.2:
                        cluster["propositions"].append(prop)
                        cluster["summary"] = self._update_summary(cluster["propositions"])
                        assigned = True
                        break
            if not assigned:
                clusters.append({
                    "id": str(uuid.uuid4()),
                    "title": f"Thematic Unit: {prop[:30]}...",
                    "summary": prop,
                    "propositions": [prop]
                })

        chunks = []
        for idx, cluster in enumerate(clusters):
            combined_content = " ".join(cluster["propositions"]).strip()
            chunks.append(Chunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                content=combined_content,
                chunk_index=idx,
                strategy=ChunkingStrategy.AGENTIC,
                character_count=len(combined_content),
                token_estimate=max(1, len(combined_content) // 4),
                metadata={
                    "thematic_title": cluster["title"],
                    "propositions_count": len(cluster["propositions"])
                }
            ))
        return chunks

    def _extract_propositions(self, text: str) -> List[str]:
        # Split on sentence boundaries and newlines
        sentences = re.split(r"(?<=[.?!;])\s+|\n+", text)
        propositions = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # Further split long compound sentences by conjunctions
            clauses = re.split(r"\s+(?:and|but|however|therefore|whereas)\s+", s, flags=re.IGNORECASE)
            for c in clauses:
                c_clean = c.strip()
                if len(c_clean) > 12:
                    propositions.append(c_clean)
        return propositions if propositions else [text.strip()]

    def _compute_thematic_overlap(self, prop: str, summary: str) -> float:
        set1 = set(re.findall(r"\w+", prop.lower()))
        set2 = set(re.findall(r"\w+", summary.lower()))
        if not set1 or not set2:
            return 0.0
        return len(set1 & set2) / len(set1 | set2)

    def _update_summary(self, propositions: List[str]) -> str:
        return " | ".join(propositions[-2:])

def get_chunker(strategy: ChunkingStrategy, **kwargs) -> BaseChunker:
    """Factory creating chunker instances by strategy."""
    if strategy == ChunkingStrategy.CHARACTER:
        return CharacterChunker(
            chunk_size=kwargs.get("chunk_size", 350),
            chunk_overlap=kwargs.get("chunk_overlap", 35)
        )
    elif strategy == ChunkingStrategy.RECURSIVE:
        return RecursiveCharacterChunker(
            chunk_size=kwargs.get("chunk_size", 400),
            chunk_overlap=kwargs.get("chunk_overlap", 40)
        )
    elif strategy == ChunkingStrategy.DOCUMENT_SPECIFIC:
        return DocumentSpecificChunker(
            chunk_size=kwargs.get("chunk_size", 500)
        )
    elif strategy == ChunkingStrategy.SEMANTIC:
        return SemanticChunker(
            embedding_provider=kwargs.get("embedding_provider"),
            buffer_size=kwargs.get("buffer_size", 1),
            breakpoint_percentile=kwargs.get("breakpoint_percentile", 90.0)
        )
    elif strategy == ChunkingStrategy.AGENTIC:
        return AgenticPropositionChunker(
            max_propositions_per_chunk=kwargs.get("max_propositions_per_chunk", 4)
        )
    return RecursiveCharacterChunker()
