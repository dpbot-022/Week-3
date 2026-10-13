import re
import unicodedata
from typing import List, Dict, Any, Tuple
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from src.core.logging import logger

VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
]
VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]
]

def validate_aadhaar_verhoeff(number_str: str) -> bool:
    """Validates 12-digit Indian Aadhaar number using the Verhoeff checksum algorithm."""
    clean = re.sub(r"\D", "", number_str)
    if len(clean) != 12:
        return False
    # Aadhaar numbers cannot start with 0 or 1
    if clean[0] in ("0", "1"):
        return False
    c = 0
    for i, char in enumerate(reversed(clean)):
        digit = int(char)
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][digit]]
    return c == 0

class PIIGuardrail:
    """Enterprise Indian PII and Secrets detection guardrail backed by Microsoft Presidio.
    Applies NFKC normalization and zero-width/bidi stripping before detection."""

    def __init__(self):
        self._init_presidio()

    def _init_presidio(self):
        try:
            conf = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
            }
            provider = NlpEngineProvider(nlp_configuration=conf)
            self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
            logger.info("Presidio AnalyzerEngine initialized with en_core_web_sm.")
        except Exception as e:
            logger.warning(f"Could not initialize Presidio with spacy model: {e}. Falling back to default pattern engine.")
            self.analyzer = None

    @staticmethod
    def sanitize_input(text: str) -> str:
        """Strips zero-width spaces, bidi overrides, and normalizes via Unicode NFKC."""
        if not text:
            return ""
        # 1. Unicode NFKC normalization
        norm = unicodedata.normalize("NFKC", text)
        # 2. Strip zero-width & bidi characters
        cleaned = re.sub(r"[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E\u2066-\u2069]", "", norm)
        return cleaned

    # Custom India Patterns & Secrets
    PATTERNS = {
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
        "PHONE_NUMBER": r"\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})\b",
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "PAN": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        "GSTIN": r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b",
        "IFSC": r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
        "INDIAN_MOBILE": r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
        "SECRET_KEY": r"\b(?:sk-[a-zA-Z0-9]{20,48}|ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{40,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z-_]{35}|Bearer\s+[a-zA-Z0-9_\-\.]{25,}|-----BEGIN [A-Z ]+ PRIVATE KEY-----)\b",
        "CREDIT_CARD": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b"
    }

    AADHAAR_REGEX = r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"

    def detect(self, text: str) -> List[Dict[str, Any]]:
        clean_text = self.sanitize_input(text)
        findings: List[Dict[str, Any]] = []
        seen_spans = set()

        # 1. Custom India & Secret Pattern Detection
        for pii_type, regex in self.PATTERNS.items():
            for match in re.finditer(regex, clean_text):
                span = (match.start(), match.end())
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                findings.append({
                    "entity_type": pii_type,
                    "start": match.start(),
                    "end": match.end(),
                    "text": match.group(0),
                    "confidence": 0.95
                })

        # 2. Aadhaar with Verhoeff Checksum Verification
        for match in re.finditer(self.AADHAAR_REGEX, clean_text):
            val = match.group(0)
            if validate_aadhaar_verhoeff(val):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    findings.append({
                        "entity_type": "AADHAAR",
                        "start": match.start(),
                        "end": match.end(),
                        "text": val,
                        "confidence": 1.0
                    })

        # 3. Microsoft Presidio standard analyzer
        if self.analyzer:
            try:
                results = self.analyzer.analyze(text=clean_text, language="en", score_threshold=0.6)
                for res in results:
                    span = (res.start, res.end)
                    if span not in seen_spans and res.entity_type in ("EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "IBAN_CODE", "CREDIT_CARD"):
                        seen_spans.add(span)
                        findings.append({
                            "entity_type": res.entity_type,
                            "start": res.start,
                            "end": res.end,
                            "text": clean_text[res.start:res.end],
                            "confidence": res.score
                        })
            except Exception as e:
                logger.error(f"Presidio analyze error: {e}")

        findings.sort(key=lambda x: x["start"])
        return findings

    def redact(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        clean_text = self.sanitize_input(text)
        findings = self.detect(clean_text)
        if not findings:
            return clean_text, []

        findings_sorted = sorted(findings, key=lambda f: f["start"], reverse=True)
        sanitized = clean_text

        for f in findings_sorted:
            placeholder = f"[{f['entity_type']}_REDACTED]"
            sanitized = sanitized[:f["start"]] + placeholder + sanitized[f["end"]:]

        return sanitized, findings

pii_guard = PIIGuardrail()
