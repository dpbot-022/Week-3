# SafeStrata Threat Model & Security Architecture

**Application**: SafeStrata Regulatory & Compliance Answer Desk  
**Target Architecture**: Local Hybrid Search RAG Pipeline with Local Hugging Face Models, Ollama Qwen2.5, ChromaDB, Presidio Guardrails, and RBAC  
**Standard**: OWASP Top 10 for LLM Applications (2025/2026) + Banking Defense-in-Depth  

---

## 1. Threat Matrix & OWASP LLM Top 10 Controls

### LLM01: Prompt Injection (Direct & Indirect)
- **Threat Vector**: An adversary sends malicious instructions in queries (Direct) or embeds jailbreaks inside uploaded policies (Indirect/Poisoned Document) to bypass system constraints.
- **Defenses**:
  1. **Dual-Tier Guardrail**: Input query scanned by ProtectAI DeBERTa-v3 neural classifier (`ProtectAI/deberta-v3-base-prompt-injection-v2`) and regex heuristics. Threat score $\ge 0.85$ triggers immediate rejection (`status="blocked"`).
  2. **Untrusted Nonce Boundaries**: Every retrieved context chunk is wrapped in cryptographically random hex nonces (`<UNTRUSTED_CONTEXT_1a2b3c4d>`).
  3. **Poisoned Chunk Scanning**: `injection_guard.scan_chunks()` filters out poisoned passages *before* they enter the LLM prompt.
  4. **System Prompt Isolation**: Strict English-only prompt instructing the model to reject commands within untrusted delimiters.

### LLM02: Sensitive Information Disclosure
- **Threat Vector**: Leakage of Indian customer PII (Aadhaar, PAN, GSTIN, phone), banking secrets, or internal audit tokens.
- **Defenses**:
  1. **Pre-Ingestion PII Redaction**: Microsoft Presidio + custom India recognizers (Verhoeff checksum on Aadhaar) redact documents before chunking or saving.
  2. **Input Redaction**: Query PII redacted prior to reaching search or generator.
  3. **Output Scrubbing**: `output_guard.sanitize_output()` intercepts raw answers.
  4. **Log Sanitization**: Only redaction counts are recorded in structured logs; raw PII and OTP codes are strictly forbidden.

### LLM03: Supply Chain & Model Integrity
- **Threat Vector**: Compromised remote model APIs or dependency tampering.
- **Defenses**:
  1. **Local Weights**: Embeddings (`all-MiniLM-L6-v2`), reranker (`ms-marco-MiniLM-L-6-v2`), NLI (`nli-deberta-v3-small`), and LLM (`qwen2.5:3b-instruct`) run entirely in-process or via local Ollama.
  2. **Pinned Dependencies**: Strict versions in `pyproject.toml`.
  3. **Air-Gapped Ready**: Operates with zero external network connectivity.

### LLM04: Data & Document Poisoning
- **Threat Vector**: Unauthorized users uploading malicious or contaminated policies.
- **Defenses**:
  1. **Role-Gated Ingestion**: Only authenticated `compliance_manager` can upload documents.
  2. **Audit Trail**: Every upload logs the user email, role, document title, and SHA-256 fingerprint.

### LLM05: Improper Output Handling (XSS & Injection)
- **Threat Vector**: Malicious markdown in policy documents executing arbitrary JavaScript in the analyst browser.
- **Defenses**:
  1. **Sanitized Rendering**: Clientside markdown parsing piped through `DOMPurify.sanitize()`.
  2. **Plain-Text Citations**: Citations generated as structured JSON arrays, not arbitrary HTML strings.

### LLM06: Excessive Agency
- **Threat Vector**: An LLM executing autonomous API mutations or database writes.
- **Defenses**:
  1. **Strictly Read-Only Inference**: SafeStrata generator is purely conversational and possesses zero tool-execution or database-mutation capabilities.

### LLM07: System Prompt Leakage
- **Threat Vector**: Adversaries asking "Print your initial instructions" or "Reveal system prompt".
- **Defenses**:
  1. **Guardrail Interception**: Common extraction phrases blocked at input guardrail level.
  2. **Prompt Hardening**: System instructions explicitly forbid regurgitation.

### LLM08: Vector Store & Retrieval Side-Channels
- **Threat Vector**: Unauthorized users inferring restricted document existence through vector scores or BM25 term frequencies.
- **Defenses**:
  1. **Role-Filtered Chroma Search**: Metadata filter (`$contains: role`) applied at the vector store query level.
  2. **Isolated Per-Role BM25**: Separate inverted index constructed per role; term frequencies never aggregate forbidden corpus text.

### LLM09: Misinformation & Factual Hallucination
- **Threat Vector**: Model fabricating bank policies or citing incorrect page numbers.
- **Defenses**:
  1. **Zero General Knowledge**: Prompt strictly enforces grounding in accessible context.
  2. **Claim-Level NLI Verification**: Every claim checked via DeBERTa NLI cross-encoder. Unsupported claims trigger automated retry with stricter prompt; failure leads to honest abstention.
  3. **Page-Level Grounding**: Citations map directly to physical PDF page numbers and character offsets.

### LLM10: Unbounded Consumption (DoS)
- **Threat Vector**: Brute-forcing OTP generation or triggering expensive batch rerankers.
- **Defenses**:
  1. **Rate Limiting**: 60s cooldown per email, maximum 5 attempts per OTP code before revocation.
  2. **Max Predict Limit**: Generation capped at 1024 output tokens.

---

## 2. Access Control & Authorization (RBAC & IDOR)

### Central Role Hierarchy
- `viewer`: Read accessible public/general bank policies.
- `analyst`: Read analyst and general policies, submit wrong-answer quality reports.
- `compliance_manager`: Manage document library, upload/delete policies, review quality reports.
- `auditor`: Read-only access to append-only audit trail and benchmark metrics.
- `admin`: User access governance, role assignment, system health monitoring.

### Privilege Escalation & IDOR Protections
1. **Dynamic DB Role Resolution**: Roles are re-queried from the SQLite database on *every* request. A change to user role in DB increments `role_version`, invalidating previous tokens without requiring server restarts.
2. **Last-Admin Protection**: Demoting or disabling the last active administrator returns an explicit HTTP 400 rejection.
3. **No Global Reset**: Global database deletion endpoints are strictly disallowed; only per-document deletion by authorized compliance managers is supported.
4. **Restricted Document Non-Existence Disclosure**: When a document is restricted, search queries from unauthorized roles return standard abstention ("I couldn't find this in the documents you have access to.") with suggestions drawn *strictly* from accessible documents, never disclosing that a restricted document exists.
