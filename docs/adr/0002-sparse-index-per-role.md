# ADR 0002: Sparse Keyword Search - Per-Role BM25 Indices

## Status
Accepted

## Context
Dense vector search excels at semantic generalization, but struggles with exact alphanumeric identifiers, regulatory circular numbers (e.g., `RBI/2016-17/18`), statutory thresholds, and section numbers.
BM25Okapi provides exact lexical scoring. However, traditional BM25 inverted indices do not support dynamic post-filtering without leaking index statistics (such as document frequency `df` and inverse document frequency `idf`) across role boundaries. If an index contains restricted documents, the IDF of a term reflects terms in forbidden documents, creating a subtle statistical side-channel.

## Decision
We implement **one independent `rank_bm25` index per role** (`viewer`, `analyst`, `compliance_manager`, `auditor`, `admin`):
- **Index Isolation**: At startup, `BM25Manager` queries the persistent SQLite `chunk_records` table and builds a distinct `BM25Okapi` inverted index for each role containing *only* the chunks authorized for that role.
- **Dynamic Rebuild**: Whenever a document is ingested, deleted, or its `allowed_roles` access list modified via the API, the corresponding per-role BM25 indices are immediately rebuilt in memory.
- **Fusion**: Dense and sparse results are merged using Reciprocal Rank Fusion ($k=60$).

## Consequences
- **Positive**: Complete absence of statistical or token leakage in sparse retrieval. Queries from an unauthorized role can never score against or be influenced by restricted documents.
- **Negative**: Memory footprint scales linearly with the number of roles; however, for bank policy corpuses (< 50,000 chunks), RAM usage is negligible (< 50 MB total).
