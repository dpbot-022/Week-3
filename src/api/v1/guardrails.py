import time
from fastapi import APIRouter, Header, HTTPException, status
from typing import Optional
from src.schemas.models import GuardrailCheckRequest, GuardrailReport, GuardrailAuditReport, PIIEntityInfo
from src.guardrails.pii_guard import pii_guard
from src.guardrails.injection_guard import injection_guard
from src.core.config import settings

router = APIRouter(prefix="/guardrails", tags=["Security & Guardrails"])

@router.post("/check", response_model=GuardrailReport)
async def check_guardrails(request: GuardrailCheckRequest):
    """Public evaluation endpoint: returns verdict, generic reason, and PII offset counts.
    Never exposes internal regex patterns or raw PII values.
    """
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
    reason = "Potential adversarial prompt injection detected" if inj_threat else None

    # Cast to PIIEntityInfo
    pii_entities = [PIIEntityInfo(**f) for f in pii_findings]

    return GuardrailReport(
        is_safe=not inj_threat,
        injection_detected=inj_threat,
        injection_score=inj_score,
        reason=reason,
        pii_detected=len(pii_entities) > 0,
        pii_entities=pii_entities,
        sanitized_text=sanitized,
        latency_ms=latency
    )

@router.post("/audit", response_model=GuardrailAuditReport)
async def audit_guardrails(
    request: GuardrailCheckRequest,
    x_audit_token: Optional[str] = Header(None, alias="X-Audit-Token")
):
    """Authenticated audit endpoint: requires valid X-Audit-Token.
    Returns internal pattern rules and detailed detection diagnostics.
    """
    if not x_audit_token or x_audit_token != settings.AUDIT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Audit-Token header."
        )

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
    reason = "Potential adversarial prompt injection detected" if inj_threat else None
    pii_entities = [PIIEntityInfo(**f) for f in pii_findings]

    return GuardrailAuditReport(
        is_safe=not inj_threat,
        injection_detected=inj_threat,
        injection_score=inj_score,
        reason=reason,
        injection_patterns=inj_patterns,
        pii_detected=len(pii_entities) > 0,
        pii_entities=pii_entities,
        sanitized_text=sanitized,
        latency_ms=latency
    )
