from typing import Optional, List
import re
from src.embeddings.provider import embedding_provider
from src.core.logging import logger

class HyDEQueryRewriter:
    """Hypothetical Document Embeddings (HyDE) & Multi-Query Expander."""
    def __init__(self):
        pass

    def generate_hypothetical_document(self, query: str) -> str:
        """Generates a hypothetical document snippet that answers the query."""
        # Domain expansion heuristic template
        clean_q = query.strip().rstrip("?")
        hypothetical_doc = (
            f"Regarding {clean_q}: The core mechanisms, architectural principles, "
            f"and established facts demonstrate that {clean_q} operates through "
            f"structured processing, verified configurations, and defined protocols. "
            f"Key factors include technical specifications, implementation details, and workflow execution."
        )
        return hypothetical_doc

    def expand_query(self, query: str) -> List[str]:
        """Expands user query into normalized search variations."""
        variations = [query]
        # Remove punctuation
        no_punct = re.sub(r"[^\w\s]", "", query).strip()
        if no_punct and no_punct != query:
            variations.append(no_punct)
        
        # Add hypothetical answer
        hypo = self.generate_hypothetical_document(query)
        variations.append(hypo)
        return variations

    def get_hyde_embedding(self, query: str) -> List[float]:
        """Embeds hypothetical document rather than raw query alone."""
        hypo = self.generate_hypothetical_document(query)
        # Average the query vector with the hypothetical document vector
        q_vec = embedding_provider.encode(query)
        h_vec = embedding_provider.encode(hypo)
        combined = 0.5 * q_vec + 0.5 * h_vec
        norm = float(sum(x ** 2 for x in combined) ** 0.5)
        if norm > 0:
            combined = combined / norm
        return combined.tolist()

hyde_rewriter = HyDEQueryRewriter()
