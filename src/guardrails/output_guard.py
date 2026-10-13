import re
import threading
from typing import Tuple, List, Dict, Any, Optional
import numpy as np
from src.core.config import settings
from src.core.logging import logger
from src.guardrails.pii_guard import pii_guard

class OutputGuardrail:
    """Validates generated LLM responses for faithfulness via cross-encoder NLI model,
    claim-level support checks, and PII leakage scrubbing."""

    def __init__(self):
        self._nli_model = None
        self._lock = threading.Lock()

    def _get_nli_model(self):
        if self._nli_model is None:
            with self._lock:
                if self._nli_model is None:
                    try:
                        from sentence_transformers import CrossEncoder
                        logger.info(f"Loading NLI cross-encoder model: {settings.NLI_MODEL}")
                        self._nli_model = CrossEncoder(settings.NLI_MODEL)
                        logger.info("NLI cross-encoder loaded successfully.")
                    except Exception as e:
                        logger.warning(f"Could not load NLI model ({e}). Using lexical fallback.")
                        self._nli_model = False
        return self._nli_model if self._nli_model is not False else None

    def sanitize_output(self, output_text: str) -> Tuple[str, bool, List[Dict[str, Any]]]:
        """Ensures generated response does not leak internal PII."""
        sanitized, findings = pii_guard.redact(output_text)
        has_pii = len(findings) > 0
        return sanitized, has_pii, findings

    def check_faithfulness(self, answer: str, context_chunks: List[str]) -> Tuple[float, List[str]]:
        """Calculates claim-level factual grounding of answer sentences against context chunks using NLI.
        Returns (faithfulness_score, unsupported_claims)."""
        if not answer or not context_chunks:
            return 0.0, ["No context provided for validation."]

        # Split answer into claim sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", answer) if len(s.strip()) > 8]

        if not sentences:
            return 1.0, []

        nli = self._get_nli_model()
        supported_count = 0
        unsupported = []

        # Clean conversational boilerplate before NLI check
        clean_sentences = []
        for s in sentences:
            c = re.sub(r"\[\d+\]", "", s).strip()
            c = re.sub(r"^(?:based on (?:the )?(?:provided )?(?:context|documents?|records?|information|passages?)(?: provided)?[,\s:]*|according to [^,.:]+[,\s:]*)", "", c, flags=re.I).strip()
            clean_sentences.append(c if len(c) > 5 else s)

        premises = context_chunks[:5]

        for sent_idx, clean_sent in enumerate(clean_sentences):
            sent_supported = False
            claim_tokens = set(re.findall(r"\b[a-zA-Z0-9_]{3,}\b", clean_sent.lower()))

            for prem in premises:
                prem_tokens = set(re.findall(r"\b[a-zA-Z0-9_]{3,}\b", prem.lower()))
                overlap_ratio = len(claim_tokens & prem_tokens) / max(1, len(claim_tokens)) if claim_tokens else 1.0

                if nli:
                    try:
                        logits = nli.predict([(prem, clean_sent)])
                        exp_l = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                        probs = exp_l / np.sum(exp_l, axis=1, keepdims=True)
                        is_contradiction = float(probs[0, 0]) > 0.45
                        entailment_prob = float(probs[0, 1])

                        # Grounded if non-contradictory AND (entailed or high factual overlap)
                        if not is_contradiction and (entailment_prob >= settings.NLI_SUPPORT_THRESHOLD or overlap_ratio >= 0.35):
                            sent_supported = True
                            break
                    except Exception as e:
                        logger.error(f"NLI prediction error: {e}")
                        if overlap_ratio >= 0.4:
                            sent_supported = True
                            break
                else:
                    if overlap_ratio >= 0.4:
                        sent_supported = True
                        break

            if sent_supported:
                supported_count += 1
            else:
                unsupported.append(sentences[sent_idx])

        faithfulness_score = round(supported_count / len(sentences), 2)
        return faithfulness_score, unsupported

output_guard = OutputGuardrail()
