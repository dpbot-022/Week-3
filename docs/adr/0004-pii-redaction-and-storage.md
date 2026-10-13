# ADR 0004: PII Redaction & Non-Storage Architecture

## Status
Accepted

## Context
Under Indian banking regulatory frameworks (including RBI Master Direction on IT Governance and the Digital Personal Data Protection Act, DPDP 2023), banks must protect customer Personally Identifiable Information (PII) including PAN, Aadhaar, GSTIN, IFSC, phone numbers, and authentication secrets.
Adversarial attacks may attempt to smuggle PII via prompt injection, zero-width spaces, or homoglyphs.

## Decision
We implement a multi-stage defense-in-depth PII guardrail using **Microsoft Presidio** supplemented by custom Indian regulatory recognizers:
1. **Normalization Pre-Processing**: Before detection, every string undergoes Unicode NFKC normalization and stripping of zero-width (`\u200B-\u200D`, `\uFEFF`) and bidirectional control characters.
2. **Indian Statutory Recognizers**:
   - **PAN**: RegEx validation (`[A-Z]{5}[0-9]{4}[A-Z]`).
   - **Aadhaar**: 12-digit detection with mathematical **Verhoeff Checksum** algorithm verification (`c == 0`).
   - **GSTIN**: 15-character statutory format validation.
   - **IFSC**: 11-character bank branch alphanumeric structure.
   - **Indian Mobile**: Standard `+91` and `[6-9]\d{9}` mobile prefix patterns.
   - **Secrets**: API keys (`sk-`, `ghp_`, `AKIA`, `AIza`), JWT tokens, private keys.
3. **Four-Point Enforcement**:
   - **Input**: Redacted before query reaches retrieval or LLM prompt.
   - **Ingestion**: Documents are redacted *before* chunking, embedding, or writing to disk.
   - **Output**: LLM-generated responses scrubbed before returning to caller.
   - **Logs**: Structured logs format PII fields as redaction counts only. Raw PII, secrets, and OTPs are never logged.

## Consequences
- **Positive**: Strict regulatory compliance, complete mitigation of PII data exfiltration attacks.
- **Negative**: High sensitivity might flag test data; mitigated by context checking and Verhoeff validation.
