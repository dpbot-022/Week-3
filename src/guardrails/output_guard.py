import re
from typing import Tuple, List, Dict, Any
from src.guardrails.pii_guard import pii_guard

class OutputGuardrail:
    """Validates generated LLM responses for faithfulness, hallucinations, and PII leaks."""

    def sanitize_output(self, output_text: str) -> Tuple[str, bool, List[Dict[str, Any]]]:
        """Ensures generated response does not leak internal PII."""
        sanitized, findings = pii_guard.redact(output_text)
        has_pii = len(findings) > 0
        return sanitized, has_pii, findings

    def check_faithfulness(self, answer: str, context_chunks: List[str]) -> Tuple[float, List[str]]:
        """Calculates factual grounding of answer sentences against context chunks."""
        if not answer or not context_chunks:
            return 0.0, ["No context provided for validation."]

        combined_context = " ".join(context_chunks).lower()
        sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", answer) if len(s.strip()) > 10]
        
        if not sentences:
            return 1.0, []

        supported_count = 0
        unsupported = []

        for sent in sentences:
            # Extract key informative words (words > 4 chars)
            words = [w for w in re.findall(r"\b[a-zA-Z]{4,}\b", sent.lower()) if w not in [
                "this", "that", "these", "those", "which", "there", "their", "about", "would", "could", "should"
            ]]
            if not words:
                supported_count += 1
                continue
            
            # Check overlap against context
            overlap = sum(1 for w in words if w in combined_context)
            ratio = overlap / len(words)
            if ratio >= 0.5:
                supported_count += 1
            else:
                unsupported.append(sent)

        faithfulness_score = round(supported_count / len(sentences), 2)
        return faithfulness_score, unsupported

output_guard = OutputGuardrail()
