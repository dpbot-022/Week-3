from typing import List, Set
import re
from src.schemas.models import ScoredChunk

class ContextDeduplicator:
    """Removes semantically and textually redundant chunks to maximize context diversity."""
    def __init__(self, jaccard_threshold: float = 0.70):
        self.jaccard_threshold = jaccard_threshold

    def _get_shingles(self, text: str, k: int = 3) -> Set[str]:
        words = re.findall(r"\w+", text.lower())
        if len(words) < k:
            return {" ".join(words)} if words else set()
        return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}

    def deduplicate(self, chunks: List[ScoredChunk], max_chunks: int = 5) -> List[ScoredChunk]:
        if not chunks:
            return []

        unique_chunks: List[ScoredChunk] = []
        seen_shingles: List[Set[str]] = []

        for chunk in chunks:
            shingles = self._get_shingles(chunk.content)
            is_duplicate = False

            for existing_shingles in seen_shingles:
                if not shingles or not existing_shingles:
                    continue
                intersection = len(shingles & existing_shingles)
                union = len(shingles | existing_shingles)
                jaccard = intersection / union if union > 0 else 0.0

                if jaccard >= self.jaccard_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_chunks.append(chunk)
                seen_shingles.append(shingles)

            if len(unique_chunks) >= max_chunks:
                break

        return unique_chunks

deduplicator = ContextDeduplicator()
