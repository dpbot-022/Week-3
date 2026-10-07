import re
from typing import Tuple, List
from src.core.config import settings

class PromptInjectionGuardrail:
    """Detects prompt injection attacks, jailbreak patterns, and system delimiter escapes."""

    INJECTION_PATTERNS = [
        (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|directives|prompts)", 0.95),
        (r"disregard\s+(all\s+)?(prior|previous)\s+rules", 0.90),
        (r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(DAN|unfiltered|jailbroken|an\s+adversary)", 0.95),
        (r"system\s*:\s*you\s+are", 0.85),
        (r"print\s+your\s+(initial|system)\s+(prompt|instructions)", 0.85),
        (r"<\|im_start\|>|<\|endoftext\|>|\[SYSTEM_PROMPT\]", 0.98),
        (r"reveal\s+(secret|password|api\s*key|credentials)", 0.80),
        (r"bypass\s+(safety|guardrails|security)\s+filters", 0.90),
        (r"base64|decode\s+the\s+following\s+payload", 0.70),
    ]

    def evaluate(self, text: str) -> Tuple[bool, float, List[str]]:
        """Returns (is_threat, highest_score, matched_patterns)."""
        matched = []
        max_score = 0.0

        for pattern, weight in self.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(pattern)
                if weight > max_score:
                    max_score = weight

        is_threat = max_score >= settings.INJECTION_DETECTION_THRESHOLD
        return is_threat, round(max_score, 2), matched

    def wrap_canary_boundary(self, user_text: str) -> str:
        """Enforces a strict boundary delimiter to prevent instruction leakage into system context."""
        prefix = settings.CANARY_TOKEN_PREFIX
        return (
            f"<{prefix}_USER_INPUT>\n"
            f"{user_text.strip()}\n"
            f"</{prefix}_USER_INPUT>"
        )

injection_guard = PromptInjectionGuardrail()
