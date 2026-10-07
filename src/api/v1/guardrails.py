import time
from fastapi import APIRouter
from src.schemas.models import GuardrailCheckRequest, GuardrailReport
from src.guardrails.pii_guard import pii_guard
from src.guardrails.injection_guard import injection_guard

router = APIRouter(prefix="/guardrails", tags=["Security & Guardrails"])

@router.post("/check", response_model=GuardrailReport)
async def check_guardrails(request: GuardrailCheckRequest):
    """Evaluates text against PII patterns and Prompt Injection/Jailbreak attempts."""
    start_time = time.time()
    
    inj_threat = False
    inj_score = 0.0
    inj_patterns = []
    if request.check_injection:
        inj_threat, inj_score, inj_patterns = injection_guard.evaluate(request.text)

    sanitized = request.text
    pii_findings = []
    if request.check_pii:
        sanitized, pii_findings = pii_guard.redact(request.text)

    latency = round((time.time() - start_time) * 1000, 2)

    return GuardrailReport(
        is_safe=not inj_threat,
        injection_detected=inj_threat,
        injection_score=inj_score,
        injection_patterns=inj_patterns,
        pii_detected=len(pii_findings) > 0,
        pii_entities=pii_findings,
        sanitized_text=sanitized,
        latency_ms=latency
    )
