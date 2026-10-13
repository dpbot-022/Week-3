# SafeStrata Changelog

All notable changes to the SafeStrata compliance and regulatory answer desk are documented in this file.

## [Unreleased]

### Phase 3 & 4: Neural LLM, NLI Verification & Multi-Tier Guardrails (Branch `phase-3-llm-guardrails`)
- **LLM Engine**: Integrated local Ollama service running `qwen2.5:3b-instruct` with strict English-only prompt, temperature $\le 0.2$, token budget enforcement, and per-request cryptographically random nonce delimiters (`<UNTRUSTED_CONTEXT_nonce>`).
- **Extractive Fallback**: Explicit 503 or labeled "Extractive mode" when Ollama is unreachable; zero hallucinations or fabricated answers.
- **Faithfulness Verification**: Claim-level NLI support check via `cross-encoder/nli-deberta-v3-small`. One automated retry with strict system prompt on check failure, followed by honest abstention if unsupported claims persist.
- **PII Guardrails**: Enterprise Microsoft Presidio integration with custom India recognizers (PAN, Aadhaar with Verhoeff checksum algorithm and context heuristics, GSTIN, IFSC, Indian mobile) plus secrets detector (`sk-`, `ghp_`, `AKIA`, private keys). NFKC normalization and zero-width/bidi stripping applied prior to every detector across inputs, ingestion, outputs, and structured logs.
- **Prompt Injection Defense**: Dual-tier classifier combining ProtectAI DeBERTa-v3 neural classifier (`ProtectAI/deberta-v3-base-prompt-injection-v2`) and heuristic pattern regexes. Applied to both user queries and individual retrieved chunks before entering prompts.
- **Intent Routing**: Deterministic non-LLM scope and greeting router displaying accessible policy titles based on caller role.

### Phase 2: Authentic RBI Regulatory Corpus & Synthetic Fixtures (Branch `phase-2-corpus-ingestion`)
- Ingested 3 authentic public Reserve Bank of India (RBI) directions comprising 190 pages:
  - *RBI Master Direction - Know Your Customer (KYC) Direction, 2016* (102 pages)
  - *RBI Master Direction on IT Governance, Risk, Controls and Assurance Practices, 2023* (52 pages)
  - *RBI Guidelines on Digital Lending, 2022* (36 pages)
- Ingested 4 synthetic policy and audit fixtures with labeled roles:
  - *Employee Leave & Attendance Policy 2026* (all roles)
  - *IT Security & Access Control Policy* (analyst, compliance_manager)
  - *Confidential Internal Audit AML Memo* (compliance_manager only with canary `AUDIT_REF_AML_2026_XYZ99`)
  - *Customer KYC Records with Synthetic PII* (redacted at ingestion)
- Added `scripts/prepare_corpus.py`, `scripts/seed_corpus.py`, and `make seed-corpus`.
- 60 passing automated unit/integration tests with 87% coverage.

### Phase 1: Persistence, RBAC & Leakage Prevention (Branch `phase-1-rbac-retrieval-leakage`)
- Implemented SQLite database (`data/safestrata.db`) via SQLAlchemy models (`users`, `documents`, `chunk_records`, `audit_logs`, `otp_tokens`, `wrong_answer_reports`).
- Implemented central role hierarchy (`viewer`, `analyst`, `compliance_manager`, `auditor`, `admin`) with `require_permission()` on all non-public endpoints.
- Role resolution verified on every request with `role_version` checking for immediate revocation.
- Role-filtered dense ChromaDB queries and per-role sparse BM25 indices fused via RRF ($k=60$).
- Passed RBAC permission matrix and retrieval leakage test suites.
