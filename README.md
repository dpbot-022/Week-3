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

### 3. Seed Demo Data & Run
```bash
# Seed local knowledge base
python scripts/seed_demo_data.py

# Start server with uvicorn
uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload
```
Open your browser at:
- **Interactive Web Playground**: [http://localhost:8001/](http://localhost:8001/)
- **Interactive OpenAPI / Swagger Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)

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
| **Dense Only** (`all-MiniLM-L6-v2`) | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 25.0% [12.5%, 40.0%] | 25.0% [12.5%, 40.0%] |
| **Sparse Only** (`BM25Okapi`) | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 25.0% [12.5%, 40.0%] | 25.0% [12.5%, 40.0%] |
| **Hybrid (RRF)** | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 25.0% [12.5%, 40.0%] | 25.0% [12.5%, 40.0%] |
| **Hybrid + Cross-Encoder Reranker** | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 25.0% [12.5%, 40.0%] | 25.0% [12.5%, 40.0%] |
| **Hybrid + Cross-Encoder + HyDE** | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 27.5% [15.0%, 42.5%] | 25.0% [12.5%, 40.0%] | 25.0% [12.5%, 40.0%] |

*Measured on $N=40$ gold test questions (SHA-256 `bb0bb8b69cc4`). p50 Latency: 4.04 ms, p95 Latency: 5.51 ms (warm-up excluded). Git SHA: `f82526d`. Evaluation run: `2026-10-12T03:59:20.234896+00:00`.*
<!-- EVAL_TABLE_END -->

*(Full methodology, ablations, and system boundaries detailed in [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md).)*

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
