# SafeStrata System Limitations & Scope Boundaries

This document provides transparent documentation of known engineering boundaries, model limitations, security bypass vectors, and evaluation scopes for SafeStrata.

---

## 1. LLM Size Limits & Generation Constraints
- **Local Fallback Mode**: The embedded extractive synthesis engine operates as an extractive, extractive-summarization local pipeline when no cloud API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) are supplied. It does not possess generative reasoning beyond synthesis over retrieved spans.
- **Context Window Bounds**: Local dense embedding (`all-MiniLM-L6-v2`) and cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) models have maximum sequence length limits of 256 and 512 wordpieces respectively. Content exceeding these token windows is truncated.
- **Provider Timeouts & Rate Limits**: Upstream provider calls are capped at strict 15.0s HTTP client timeouts. Rate-limited requests (HTTP 429) and upstream provider outages (HTTP 5xx) surface as explicit `503 Service Unavailable` exceptions with upstream detail.

---

## 2. Language Support
- **Monolingual English Scope**: SafeStrata's default pipelines are tuned and benchmarked exclusively for English (`en`).
- **PII Detector Tokenization**: The regex PII detector utilizes regular expressions tailored to English alphanumeric formats and standard Indian identifiers (Aadhaar `\d{4}\s?\d{4}\s?\d{4}`, PAN `[A-Z]{5}[0-9]{4}[A-Z]{1}`). It does not support non-Latin character sets or international tax IDs outside India and the US.
- **Cross-Encoder Model**: The reranker checkpoint (`cross-encoder/ms-marco-MiniLM-L-6-v2`) is pre-trained on English MS-MARCO passages. Multilingual queries will suffer severe relevance calibration loss without multilingual checkpoints (e.g. `multilingual-MiniLM`).

---

## 3. Known Guardrail Bypasses
The security tier consists of a deterministic **regex PII detector** and a signature-based **prompt injection detector**. The following bypass vectors are known and require secondary semantic defense layers for hostile threat environments:

1. **Obfuscation & Leetspeak**:
   - PII strings or injection patterns written with leetspeak (e.g., `p@ssw0rd`, `3mail[at]domain[dot]com`) or spaced characters (`d r o p   t a b l e`) may bypass regex matching.
2. **Zero-Width Characters & Unicode Encoding**:
   - Insertion of invisible zero-width spaces (`\u200B`) or homoglyph substitutions bypasses exact string and regex boundary checks unless Unicode normalization is enforced upstream.
3. **Base64 / Hex / Cipher Encoding**:
   - Encoded injection payloads (e.g., Base64 strings instructed to be decoded by an LLM) bypass static keyword heuristics.
4. **Adversarial & Multi-Turn Jailbreaks**:
   - Subtle indirect injections and narrative role-play jailbreaks ("Hypothetical scenario where instructions are overridden") are not detected by deterministic regex rules.

---

## 4. Evaluation Set Size & Domain Scope
- **Benchmark Corpus**: The gold evaluation set contains **80 query items** (40 dev, 40 test split, SHA-256 hash `bb0bb8b69cc4dc8b3099097a5be09a2ebf312816e616ba845360ee187b5fa78e`) grounded on the SafeStrata technical knowledge corpus (`production_knowledge.md`).
- **Domain Limitation**: Evaluations represent technical systems, database architecture, and hybrid retrieval domain topics. Performance metrics (Recall@5, MRR, nDCG@5) do not generalize to medical, financial, legal, or conversational open domains.
- **Bootstrap Confidence Bounds**: While non-parametric bootstrap resampling ($B=1000$) provides 95% confidence intervals, sample size $N=40$ per split yields wider confidence intervals that should be refined with larger production query logs.
