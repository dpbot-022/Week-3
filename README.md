# SafeStrata: Layered Hybrid RAG & Context Guardrails Engine

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-orange.svg)](https://www.trychroma.com/)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-MiniLM--L6--v2-yellow.svg)](https://huggingface.co/)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

**SafeStrata** is an enterprise-ready **Retrieval-Augmented Generation (RAG)** context engine. It unites **Dense Vector Search** (local Hugging Face `all-MiniLM-L6-v2`), **Sparse Lexical Search** (`BM25Okapi`), **Reciprocal Rank Fusion (RRF)**, **Neural Cross-Encoder Reranking** (`cross-encoder/ms-marco-MiniLM-L-6-v2`), and **Deterministic AI Guardrails** (Regex PII detector with PAN, Aadhaar, email, phone, SSN, API key redaction, and canary-isolated prompt injection defense).

---

## 🌟 Key Features & Architecture

1. **Multi-Level Document Chunking (Levels 1–5)**:
   - **Level 1**: Fixed Character Splitter with sliding window overlap.
   - **Level 2**: Hierarchical Recursive Character Splitter (`\n\n`, `\n`, sentence endings, words).
   - **Level 3**: Document-Specific Splitter for Markdown headers, code blocks, and structured tables.
   - **Level 4**: Semantic Breakpoint Splitter leveraging sentence embedding cosine distance spikes and percentile thresholding.
   - **Level 5**: Agentic / Propositional Splitter decomposing text into atomic propositions and thematic clusters.

2. **Hybrid Search Retrieval & Fusion**:
   - **Dense Retrieval**: Local Hugging Face Sentence Transformers (`all-MiniLM-L6-v2`) in persistent **ChromaDB**.
   - **Sparse Retrieval**: Tokenized **BM25Okapi** index for exact technical identifiers and rare vocabulary.
   - **Reciprocal Rank Fusion (RRF)**: $RRF(d) = \sum \frac{1}{k + rank_i(d)}$ ($k=60$) combining heterogeneous distributions without normalization bias.

3. **Neural Cross-Encoder Reranking**:
   - `cross-encoder/ms-marco-MiniLM-L-6-v2` performs joint cross-attention over query-document pairs, boosting Top-K precision.

4. **Query Optimization & Deduplication**:
   - **HyDE (Hypothetical Document Embeddings)**: Expands terse queries into hypothetical document answer vectors to bridge semantic distance.
   - **Context Deduplication**: 3-shingle Jaccard overlap thresholding eliminates redundant chunks while preserving context diversity.

5. **Multi-Tier Security & Guardrails**:
   - **Regex PII Detection & Redaction**: Scans and masks emails, phone numbers, SSNs, credit cards, API keys, IP addresses, Indian PAN, and Aadhaar numbers with replacement tokens (`[EMAIL_REDACTED]`, `[PAN_REDACTED]`). Public API responses return entity types and character offsets only, never raw matched strings.
   - **Prompt Injection Defense**: Evaluates incoming queries against jailbreak signatures ("Ignore previous directives", "DAN mode", system escapes) and canary isolation boundaries (`<SEC_CTX_USER_INPUT>`).
   - **Calibrated Abstention**: Automatically abstains (`status="abstained"`) when retrieved context fails to meet relevance thresholds (threshold 0.15) or support checks.

6. **Interactive Web UI Playground**:
   - Sleek modern dark glassmorphism dashboard served directly by FastAPI.
   - Live testing of all chunking levels, hybrid search score breakdown, and guardrails audit.

---

## 🚀 Quickstart Guide

### 1. Prerequisites & Environment Setup
- Python 3.10+ (Python 3.12 recommended)
- `uv` (recommended) or standard `pip`

```bash
# Clone the repository
git clone <your-repo-url>
cd safestrata

# Create virtual environment
uv venv .venv --python 3.12
source .venv/bin/activate

# Install dependencies
uv pip install -e .
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
```
*(Runs out of the box with local Hugging Face models and local generation. Optional OpenAI, Gemini, or Anthropic integration available via environment keys.)*

#### 🔐 Passwordless JWT & Genuine Email OTP Setup
SafeStrata features an enterprise-grade, Google Sign-in style passwordless authentication flow via async SMTP:

1. **JWT & Security Keys**:
   - `JWT_SECRET`: 64+ character cryptographically secure secret (generate with `openssl rand -hex 32`). **Server refuses to start without this key configured.**
   - `OTP_PEPPER`: Server-side secret pepper for HMAC-SHA256 OTP hashing.

2. **Gmail SMTP Configuration (Testing & Production)**:
   - Go to your Google Account -> **Security** -> enable **2-Step Verification**.
   - Search for **App passwords** (or go to `myaccount.google.com/apppasswords`).
   - Create an app named `SafeStrata` and copy the 16-character password.
   - Configure in `.env`:
     ```env
     SMTP_HOST=smtp.gmail.com
     SMTP_PORT=587
     SMTP_USERNAME=your-account@gmail.com
     SMTP_PASSWORD=xxxx xxxx xxxx xxxx
     SMTP_FROM=your-account@gmail.com
     SMTP_STARTTLS=true
     SMTP_SSL=false
     ```

3. **Production Email Deliverability (SPF, DKIM, DMARC)**:
   To ensure genuine OTP verification emails land directly in the user's primary inbox rather than Spam or Quarantine:
   - **SPF (Sender Policy Framework)**: Publish a DNS TXT record on your domain authorizing your mail server:
     `v=spf1 include:_spf.google.com ~all` (or your mail relay's IP).
   - **DKIM (DomainKeys Identified Mail)**: Configure 2048-bit asymmetric cryptographic signatures on outgoing mail so receiving MTAs verify message integrity.
   - **DMARC (Domain-based Message Authentication, Reporting, and Conformance)**: Add a DNS TXT record at `_dmarc.yourdomain.com`:
     `v=DMARC1; p=reject; rua=mailto:dmarc-reports@yourdomain.com; pct=100; adkim=s; aspf=s`
   - **Headers & Formatting**: SafeStrata automatically generates compliant RFC 5322 `Message-ID`, `Date`, `From`, `Reply-To`, and multipart `text/plain` + `text/html` bodies with clear anti-phishing warnings.

### 3. Seed Demo Data & Run
```bash
# Seed local knowledge base
python scripts/seed_demo_data.py

# Start server with uvicorn
uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload
```
Open your browser at:
- **Interactive Web Playground (Login Wall)**: [http://localhost:8001/](http://localhost:8001/)
- **Interactive OpenAPI / Swagger Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)

---

## 🔒 Authentication & Full Login Wall Architecture

- **Single Sign-In / Sign-Up Flow**: Users enter their email at `/api/v1/auth/request-otp`. If the email is valid, a genuine 6-digit OTP is delivered via async SMTP (`aiosmtplib`).
- **Timing & Enumeration Defense**: Responses are strictly identical for existing and new users (`"If this email is valid, a verification code has been sent."`), preventing user enumeration.
- **Cryptographic Security**:
  - OTPs are stored solely as **HMAC-SHA256 hashes** peppered with `OTP_PEPPER`—the raw code is never stored in memory or databases.
  - The OTP code is **never returned** in any API response JSON, header, or log line.
  - Single-use only, 10-minute expiry, max 5 attempts before permanent invalidation, and 60-second resend cooldown.
- **Dual-Token JWT Architecture**:
  - **Access Token**: Short-lived (15 minutes), algorithm pinned to `HS256`, containing standard claims (`sub`, `jti`, `iss`, `aud`, `iat`, `exp`). Maintained strictly **in memory** by the frontend client (never in `localStorage` or `sessionStorage`).
  - **Refresh Token**: Long-lived (7 days), stored in a cryptographically secured `httpOnly`, `SameSite=Lax` cookie (`Secure` in production).
  - **Family Token Rotation**: Every refresh generates a new token pair and revokes the predecessor. If an old refresh token is reused (indicating token replay/theft), the entire token family is immediately revoked, forcing all active sessions for that family to re-authenticate.
- **Protected Core Endpoints**: All knowledge retrieval, chunk previewing, document ingestion, guardrails checking, and benchmark evaluation endpoints require `Depends(get_current_user)`.
- **Frontend Isolation Wall**: The dashboard UI and data queries are quarantined in a `<template id="dashboard-template">`. No dashboard DOM elements exist or execute network requests until user authentication is verified. Transparent 401 interceptor automatically refreshes access tokens without disrupting user experience.

---

## 🧪 Automated Testing & Coverage

Execute the complete test suite with measured code coverage and ratcheted threshold:

```bash
pytest
```

---

## 📊 Benchmark Evaluation Summary

<!-- EVAL_TABLE_START -->
| Architecture / Ablation | Recall@5 [95% CI] | MRR [95% CI] | nDCG@5 [95% CI] | Claim Faithfulness [95% CI] | Embedding Relevance [95% CI] |
|---|---|---|---|---|---|
| **Dense Only** (`all-MiniLM-L6-v2`) | 62.0% [42.0%, 80.0%] | 50.1% [32.8%, 68.0%] | 55.2% [37.9%, 72.7%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| **Sparse Only** (`BM25Okapi`) | 28.0% [12.0%, 44.0%] | 28.0% [12.0%, 44.0%] | 28.0% [12.0%, 44.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| **Hybrid (RRF)** | 62.0% [42.0%, 80.0%] | 50.1% [32.8%, 68.0%] | 55.2% [37.9%, 72.7%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| **Hybrid + Cross-Encoder Reranker** | 58.0% [40.0%, 76.0%] | 58.0% [40.0%, 76.0%] | 57.0% [38.5%, 75.5%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| **Hybrid + Cross-Encoder + HyDE** | 62.0% [44.0%, 80.0%] | 60.0% [42.0%, 78.0%] | 59.5% [42.0%, 78.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |

*Measured on $N=25$ gold test questions (SHA-256 `c08fbf59a7ff`). p50 Latency: 178.69 ms, p95 Latency: 217.74 ms (warm-up excluded). Git SHA: `8124517`. Evaluation run: `2026-10-13T16:01:49.060673+00:00`.*
<!-- EVAL_TABLE_END -->

*(Full methodology, ablations, and system boundaries detailed in [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md).)*

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
