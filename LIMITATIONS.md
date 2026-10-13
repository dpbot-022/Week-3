# SafeStrata Limitations & Operational Boundaries

SafeStrata is engineered as an honest, deterministic compliance desk. To maintain production integrity, the system makes no exaggerated marketing claims and explicitly documents its operational boundaries.

---

## 1. Grounding & Abstention Boundaries
- **Strict In-Corpus Scope**: SafeStrata refuses to answer queries that cannot be substantiated with evidence from documents the caller is authorized to view. It will never answer from general pre-training knowledge (e.g., world history, general python programming, or foreign legislation).
- **Abstention Rate**: In our benchmark evaluation across out-of-domain and unanswerable queries, SafeStrata exhibits a 100% intentional abstention rate. It surfaces up to three suggested titles from the user's accessible library without disclosing the existence of any restricted documents.
- **Short Passage Granularity**: Chunks are currently sized at ~400 characters with 40-character overlap. Queries that require synthesizing continuous cross-tabular data spanning more than 15 pages in a single hop may produce incomplete answers unless broken down into modular queries.

## 2. LLM Reasoning Boundaries (Ollama Qwen2.5-3B-Instruct)
- **Local Model Capacity**: The 3-billion parameter model is optimized for high-throughput, low-latency execution on 16 GB RAM enterprise workstations. While it excels at factual extraction, claim synthesis, and regulatory interpretation, it does not possess the multi-step mathematical theorem proving or extensive code generation abilities of 70B+ frontier models.
- **English-Only Primary Prompt**: The current system prompts and NLI claim validation models (`cross-encoder/nli-deberta-v3-small`) are benchmarked on English regulatory texts. Non-English policy queries (e.g., Hindi, Marathi) are not formally supported.

## 3. PII & Secret Redaction Boundaries
- **Statutory Regex Precision**: Indian PII detection (Aadhaar with Verhoeff validation, PAN, GSTIN, IFSC, Indian mobile) requires adherence to statutory format conventions. Handwritten, scrambled, or heavily obfuscated PII (e.g., spelled out in phonetic words "nine eight two zero...") may evade regex heuristics unless caught by contextual Presidio entity models.
- **Secrets Coverage**: Masking covers common API keys (`sk-`, `ghp_`, `AKIA`, `AIza`, private keys). Bespoke or non-standard internal secrets without standard cryptographic entropy signatures may not be automatically redacted.

## 4. Scalability & Concurrency
- **ChromaDB SQLite Backend**: The current embedded ChromaDB vector store uses SQLite for metadata persistence. It is designed for single-node deployments supporting up to ~25 concurrent compliance analysts. For tier-1 enterprise scale (> 500 concurrent analysts), migrating to a distributed vector cluster (such as Qdrant or Milvus) is recommended.
- **In-Memory BM25 Rebuilds**: BM25 indices are rebuilt in memory after document ingestion or permission changes. While this takes < 300 ms for 1,000 chunks, corpuses exceeding 200,000 chunks will require pre-indexed Lucene or Tantivy sparse indices.
