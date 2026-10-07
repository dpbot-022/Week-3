# Enterprise Knowledge Base: Advanced RAG, Neural Reranking & AI Guardrails

## 1. Principles of Hybrid Search Retrieval
Hybrid search integrates the semantic generalization of dense vector embeddings with the lexical precision of sparse keyword search. In dense retrieval, bi-encoder language models (such as `sentence-transformers/all-MiniLM-L6-v2`) project natural language sentences into 384-dimensional continuous vector spaces. Semantic similarity is measured using cosine similarity or inner product distance, enabling search engines to surface conceptually related passages even when vocabulary disjointness occurs. Conversely, sparse retrieval leverages inverted indexes with the BM25Okapi scoring function. BM25 scores documents based on term frequency (TF), inverse document frequency (IDF), and document length normalization, excelling at rare entities, product SKUs, exact error codes, and alphanumeric identifiers.

## 2. Reciprocal Rank Fusion & Neural Cross-Encoder Reranking
Merging heterogeneous score distributions between dense cosine similarities (bounded between -1.0 and +1.0) and unbounded sparse BM25 scores presents a calibration challenge. The production-proven solution is Reciprocal Rank Fusion (RRF). RRF calculates the unified score of document $d$ as:
$$RRF(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
where $k$ is a constant smoothing parameter (commonly $k=60$) and $r_m(d)$ is the 1-based rank position of document $d$ in retrieval modality $m$.
Following initial hybrid candidate selection, a neural Cross-Encoder model (such as `cross-encoder/ms-marco-MiniLM-L-6-v2`) performs full cross-attention over the concatenated query-document pair $(q, d)$. Unlike bi-encoders that encode queries and documents independently, cross-encoders model deep token-level interactions, dramatically increasing top-k precision and filtering out superficial keyword matches.

## 3. Query Optimization: Hypothetical Document Embeddings (HyDE) & Multi-Query Expansion
Traditional user queries are short, ambiguous, and exhibit high semantic distance from comprehensive factual documents. Hypothetical Document Embeddings (HyDE) bridges this domain shift. A generative language model drafts a hypothetical document answering the user query. Even if the draft contains speculative details, its embedding resides substantially closer in vector space to relevant knowledge base documents than the initial terse query.

## 4. Knowledge Graphs & Entity Relational Traversal
While vector databases excel at unstructured passage similarity, they lack explicit relational reasoning over structured entity connections. The architecture incorporates NetworkX to maintain a directed knowledge graph ($G=(V, E)$). Named entity extraction isolates key entities across Technology, Organization, and Architectural Concepts. When a user asks a complex or multi-hop question, graph traversal traverses 1-hop and 2-hop neighbor relationships, injecting structured relational assertions directly into the prompt context.

## 5. Enterprise Guardrails: PII Redaction & Prompt Injection Mitigation
Deploying generative models in high-compliance environments demands deterministic guardrails:
1. **PII Detection and Redaction**: Incoming queries are scanned using regex and pattern detectors inspired by Microsoft Presidio. Sensitive attributes—including Email Addresses, Telephone Numbers, Social Security Numbers (SSN), Credit Card Numbers, API Keys, and IP Addresses—are redacted into structured tokens (e.g., `[EMAIL_REDACTED]`) before reaching any database or model provider.
2. **Prompt Injection & Jailbreak Defense**: Adversarial inputs attempting to override system directives (e.g., "Ignore previous instructions", "DAN mode", delimiter breakout) are scored and blocked before pipeline execution. Queries are further isolated inside canary boundary delimiters (`<SEC_CTX_USER_INPUT>`).
3. **Output Faithfulness Guard**: Generated answers are systematically evaluated against retrieved passages to ensure every factual assertion is grounded, preventing hallucinations and data leakage.
