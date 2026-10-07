import re
from typing import List, Dict, Any, Tuple

class PIIGuardrail:
    """Enterprise PII detection and redaction guardrail (Presidio pattern engine)."""
    
    PATTERNS = {
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
        "PHONE_NUMBER": r"\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})\b",
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b",
        "CREDIT_CARD": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b",
        "API_KEY": r"\b(?:sk-[a-zA-Z0-9]{20,48}|ghp_[a-zA-Z0-9]{36}|AIza[0-9A-Za-z-_]{35}|Bearer\s+[a-zA-Z0-9_\-\.]{25,})\b",
        "IP_ADDRESS": r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
    }

    def detect(self, text: str) -> List[Dict[str, Any]]:
        findings = []
        for pii_type, regex in self.PATTERNS.items():
            for match in re.finditer(regex, text):
                val = match.group(0)
                # Specific filter for SSN to avoid general 9-digit numbers unless dashed or formatted
                if pii_type == "SSN" and "-" not in val and len(val) == 9:
                    if not val.startswith(("0", "1", "2", "3", "4", "5", "6", "7")):
                        continue
                findings.append({
                    "entity_type": pii_type,
                    "start": match.start(),
                    "end": match.end(),
                    "text": val
                })
        return findings

    def redact(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        findings = self.detect(text)
        if not findings:
            return text, []

        # Sort findings in reverse order of start index to safely replace without offset shifts
        findings_sorted = sorted(findings, key=lambda f: f["start"], reverse=True)
        sanitized = text

        for f in findings_sorted:
            placeholder = f"[{f['entity_type']}_REDACTED]"
            sanitized = sanitized[:f["start"]] + placeholder + sanitized[f["end"]:]

        return sanitized, findings

pii_guard = PIIGuardrail()
