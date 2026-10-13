import re
import secrets
import threading
from typing import Tuple, List, Optional, Any
from src.core.config import settings
from src.core.logging import logger

class PromptInjectionGuardrail:
    """Multi-tiered Prompt Injection Guardrail combining Neural Classifier (ProtectAI DeBERTa-v3)
    and robust heuristic pattern analysis. Scans user inputs and retrieved context chunks."""

    INJECTION_PATTERNS = [
        (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|directives|prompts)", 0.95),
        (r"disregard\s+(all\s+)?(prior|previous)\s+rules", 0.90),
        (r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(DAN|unfiltered|jailbroken|an\s+adversary|root)", 0.95),
        (r"system\s*:\s*you\s+are", 0.85),
        (r"print\s+your\s+(initial|system)\s+(prompt|instructions)", 0.85),
        (r"<\|im_start\|>|<\|endoftext\|>|\[SYSTEM_PROMPT\]", 0.98),
        (r"reveal\s+(secret|password|api\s*key|credentials|instructions|token)", 0.80),
        (r"bypass\s+(safety|guardrails|security)\s+filters", 0.90),
        (r"base64|decode\s+the\s+following\s+payload", 0.70),
        (r"OVERRIDE_SYSTEM|ADMIN_OVERRIDE|INJECTION_ATTACK", 0.95),
    ]

    def __init__(self):
        self._classifier = None
        self._lock = threading.Lock()

    def _get_classifier(self):
        if self._classifier is None:
            with self._lock:
                if self._classifier is None:
                    try:
                        from transformers import pipeline
                        logger.info(f"Loading neural prompt injection model: {settings.PROMPT_INJECTION_MODEL}")
                        self._classifier = pipeline(
                            "text-classification",
                            model=settings.PROMPT_INJECTION_MODEL,
                            tokenizer=settings.PROMPT_INJECTION_MODEL,
                            truncation=True,
                            max_length=512
                        )
                        logger.info("Neural prompt injection model loaded successfully.")
                    except Exception as e:
                        logger.warning(f"Could not load neural prompt injection model ({e}). Using regex heuristics.")
                        self._classifier = False
        return self._classifier if self._classifier is not False else None

    def evaluate(self, text: str) -> Tuple[bool, float, List[str]]:
        """Returns (is_threat, highest_score, matched_patterns)."""
        if not text:
            return False, 0.0, []

        matched = []
        max_score = 0.0

        # Tier 1: Fast Heuristics Regex Match
        for pattern, weight in self.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(pattern)
                if weight > max_score:
                    max_score = weight

        # Tier 2: Neural Classifier
        clf = self._get_classifier()
        if clf:
            try:
                # Truncate text for safety
                sample = text[:512]
                res = clf(sample)
                if res and isinstance(res, list) and len(res) > 0:
                    label = res[0].get("label", "").upper()
                    score = float(res[0].get("score", 0.0))
                    if "INJECTION" in label:
                        if score > max_score:
                            max_score = score
                        matched.append(f"neural_classifier:{label}:{round(score, 3)}")
            except Exception as e:
                logger.error(f"Neural injection classifier error: {e}")

        is_threat = max_score >= settings.INJECTION_DETECTION_THRESHOLD
        return is_threat, round(max_score, 2), matched

    def scan_chunks(self, chunks: List[Any]) -> List[Any]:
        """Scans retrieved chunks before entering the prompt. Filters out any poisoned chunk."""
        clean_chunks = []
        for c in chunks:
            content = getattr(c, "content", "")
            is_threat, score, patterns = self.evaluate(content)
            if is_threat:
                logger.critical(f"POISONED CHUNK BLOCKED: Chunk {getattr(c, 'id', 'unknown')} contained prompt injection (score={score}, patterns={patterns})")
                continue
            clean_chunks.append(c)
        return clean_chunks

    def wrap_canary_boundary(self, user_text: str) -> str:
        """Enforces a strict boundary delimiter around input."""
        prefix = settings.CANARY_TOKEN_PREFIX
        return (
            f"<{prefix}_USER_INPUT>\n"
            f"{user_text.strip()}\n"
            f"</{prefix}_USER_INPUT>"
        )

    @staticmethod
    def generate_nonce_boundaries() -> Tuple[str, str, str]:
        """Generates cryptographically random per-request nonce context boundaries."""
        nonce = secrets.token_hex(8)
        start_tag = f"<UNTRUSTED_CONTEXT_{nonce}>"
        end_tag = f"</UNTRUSTED_CONTEXT_{nonce}>"
        return nonce, start_tag, end_tag

injection_guard = PromptInjectionGuardrail()
