"""
SafeStrata - Harness Sanity Tests
Validates the evaluation harness itself:
1. Gold spans validated against SQLite corpus chunk text.
2. Oracle retriever scores Recall@5 = 1.0, MRR = 1.0, nDCG@5 = 1.0.
3. Random retriever scores near chance (0.0).
4. Hand-computed unit tests for Recall, MRR, and nDCG across diverse rank permutations.
5. Mathematical explanation and demonstration of why the old metrics were identical.
"""

import json
import math
import sqlite3
import pytest
from pathlib import Path
from typing import List

from src.schemas.models import ScoredChunk
from src.evaluation.rag_evaluator import evaluator

DATA_PATH = Path("data/gold_eval_set.json")
DB_PATH = Path("data/safestrata.db")


def test_gold_spans_validated_against_source_text():
    """Sanity Check 1: Ensure all gold spans in gold_eval_set.json match real text in safestrata.db."""
    assert DATA_PATH.exists(), "gold_eval_set.json must exist"
    assert DB_PATH.exists(), "safestrata.db must exist"

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        gold_items = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    verified_spans = 0
    for item in gold_items:
        for span in item.get("gold_spans", []):
            chunk_id = span.get("chunk_id")
            doc_id = span["document"]
            char_start = span["char_start"]
            char_end = span["char_end"]
            expected_text = span["text"]

            # Query the database chunk
            if chunk_id:
                cursor.execute("SELECT content FROM chunk_records WHERE id = ?", (chunk_id,))
            else:
                cursor.execute(
                    "SELECT content FROM chunk_records "
                    "WHERE document_id = ? AND char_start = ? AND char_end = ?",
                    (doc_id, char_start, char_end)
                )
            row = cursor.fetchone()
            assert row is not None, f"Chunk for {doc_id} [{char_start}:{char_end}] not found in SQLite"
            db_content = row[0]
            # Verify text substring match
            assert expected_text[:50] in db_content, (
                f"Gold text '{expected_text[:50]}' not found in DB chunk: {db_content[:100]}"
            )
            verified_spans += 1

    conn.close()
    assert verified_spans >= 30, f"Expected at least 30 verified gold spans, found {verified_spans}"


def test_oracle_retriever_scores_perfect():
    """Sanity Check 2: An oracle retriever returning the exact gold chunks must score 1.0 across all retrieval metrics."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        gold_items = json.load(f)

    answerable = [item for item in gold_items if item.get("gold_spans")]
    assert len(answerable) > 0

    for item in answerable[:10]:
        gold_spans = item["gold_spans"]
        # Oracle produces chunks corresponding exactly to gold spans
        oracle_chunks = []
        for idx, span in enumerate(gold_spans):
            oracle_chunks.append(ScoredChunk(
                id=f"oracle-chunk-{idx}",
                document_id=span["document"],
                content=span["text"],
                char_start=span["char_start"],
                char_end=span["char_end"],
                final_score=1.0 - (idx * 0.05)
            ))

        metrics = evaluator.evaluate_spans(oracle_chunks, gold_spans, k=5)
        assert metrics["recall_at_k"] == 1.0, f"Oracle failed recall: {metrics}"
        assert metrics["mrr"] == 1.0, f"Oracle failed MRR: {metrics}"
        assert metrics["ndcg_at_k"] == 1.0, f"Oracle failed nDCG: {metrics}"


def test_random_retriever_scores_near_chance():
    """Sanity Check 3: A random retriever returning unrelated documents scores 0.0 on retrieval metrics."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        gold_items = json.load(f)

    answerable = [item for item in gold_items if item.get("gold_spans")]

    for item in answerable[:10]:
        gold_spans = item["gold_spans"]
        # Random retriever returns unrelated chunks from fictitious documents
        random_chunks = [
            ScoredChunk(
                id=f"noise-chunk-{i}",
                document_id="doc-unrelated-noise-001",
                content="Irrelevant random text about aerospace engineering and satellites.",
                char_start=999000 + i * 1000,
                char_end=999800 + i * 1000,
                final_score=0.10
            )
            for i in range(5)
        ]

        metrics = evaluator.evaluate_spans(random_chunks, gold_spans, k=5)
        assert metrics["recall_at_k"] == 0.0, f"Random retriever got false recall: {metrics}"
        assert metrics["mrr"] == 0.0, f"Random retriever got false MRR: {metrics}"
        assert metrics["ndcg_at_k"] == 0.0, f"Random retriever got false nDCG: {metrics}"


def test_hand_computed_retrieval_metrics():
    """Sanity Check 4: Hand-computed unit tests for recall@k, MRR, and nDCG@k."""
    gold_target_1 = {"document": "doc-a", "char_start": 100, "char_end": 500}
    gold_target_2 = {"document": "doc-b", "char_start": 200, "char_end": 600}

    # Case A: Rank 1 hit on single target -> recall=1.0, MRR=1.0, nDCG=1.0
    c_hit_rank1 = [
        ScoredChunk(id="c1", document_id="doc-a", content="match", char_start=100, char_end=500, final_score=0.9),
        ScoredChunk(id="c2", document_id="doc-noise", content="noise", char_start=0, char_end=100, final_score=0.5)
    ]
    mA = evaluator.evaluate_spans(c_hit_rank1, [gold_target_1], k=5)
    assert mA["recall_at_k"] == 1.0
    assert mA["mrr"] == 1.0
    assert mA["ndcg_at_k"] == 1.0

    # Case B: Rank 2 hit on single target -> recall=1.0, MRR=0.5, nDCG=1/log2(3) = 0.6309
    c_hit_rank2 = [
        ScoredChunk(id="c0", document_id="doc-noise", content="noise", char_start=0, char_end=100, final_score=0.9),
        ScoredChunk(id="c1", document_id="doc-a", content="match", char_start=100, char_end=500, final_score=0.8)
    ]
    mB = evaluator.evaluate_spans(c_hit_rank2, [gold_target_1], k=5)
    assert mB["recall_at_k"] == 1.0
    assert mB["mrr"] == 0.5
    expected_ndcg_rank2 = round(1.0 / math.log2(3), 4)  # ~0.6309
    assert mB["ndcg_at_k"] == expected_ndcg_rank2

    # Case C: Rank 3 hit on single target -> recall=1.0, MRR=1/3 (~0.3333), nDCG=1/log2(4) = 0.5
    c_hit_rank3 = [
        ScoredChunk(id="c0", document_id="doc-noise", content="noise", char_start=0, char_end=100, final_score=0.9),
        ScoredChunk(id="c1", document_id="doc-noise", content="noise", char_start=0, char_end=100, final_score=0.8),
        ScoredChunk(id="c2", document_id="doc-a", content="match", char_start=100, char_end=500, final_score=0.7)
    ]
    mC = evaluator.evaluate_spans(c_hit_rank3, [gold_target_1], k=5)
    assert mC["recall_at_k"] == 1.0
    assert mC["mrr"] == 0.3333
    assert mC["ndcg_at_k"] == 0.5

    # Case D: Multi-target (2 targets), hits at rank 2 and rank 4
    # DCG = 1/log2(3) + 1/log2(5) = 0.63093 + 0.43068 = 1.0616
    # IDCG = 1/log2(2) + 1/log2(3) = 1.0 + 0.63093 = 1.6309
    # nDCG = 1.0616 / 1.6309 = 0.6509
    c_multi = [
        ScoredChunk(id="c0", document_id="doc-noise", content="noise", char_start=0, char_end=100, final_score=0.9),
        ScoredChunk(id="c1", document_id="doc-a", content="match1", char_start=100, char_end=500, final_score=0.8),
        ScoredChunk(id="c2", document_id="doc-noise", content="noise", char_start=0, char_end=100, final_score=0.7),
        ScoredChunk(id="c3", document_id="doc-b", content="match2", char_start=200, char_end=600, final_score=0.6)
    ]
    mD = evaluator.evaluate_spans(c_multi, [gold_target_1, gold_target_2], k=5)
    assert mD["recall_at_k"] == 1.0
    assert mD["mrr"] == 0.5
    expected_ndcg_multi = round((1.0 / math.log2(3) + 1.0 / math.log2(5)) / (1.0 + 1.0 / math.log2(3)), 4)
    assert mD["ndcg_at_k"] == expected_ndcg_multi

    # Case E: Complete miss
    c_miss = [
        ScoredChunk(id="c0", document_id="doc-noise", content="noise", char_start=0, char_end=100, final_score=0.9)
    ]
    mE = evaluator.evaluate_spans(c_miss, [gold_target_1], k=5)
    assert mE["recall_at_k"] == 0.0
    assert mE["mrr"] == 0.0
    assert mE["ndcg_at_k"] == 0.0


def test_explanation_why_old_metrics_were_identical():
    """Sanity Check 5: Explanation & Mathematical Demonstration of Why Old Metrics Were Identical.

    MATHEMATICAL ROOT CAUSE:
    In early iterations, the evaluation dataset consisted solely of single-target questions
    where len(gold_spans) == 1.
    For any query where a retriever surfaces the single gold passage at Rank 1:
        1. Recall@k = (1 hit) / (1 gold target) = 1.0
        2. MRR = 1 / rank = 1 / 1 = 1.0
        3. nDCG@k = DCG@k / IDCG@k = (1 / log2(1 + 1)) / (1 / log2(1 + 1)) = 1.0 / 1.0 = 1.0

    Similarly, on a complete miss:
        1. Recall@k = 0.0
        2. MRR = 0.0
        3. nDCG@k = 0.0

    Because every single-target query was either an immediate Rank 1 hit or a miss,
    the values for Recall@k, MRR, and nDCG@k were strictly identical for every query!
    Averaging identical arrays produces identical aggregate means (e.g., 97.5% across all three).

    DIVERGENCE PROOF:
    When rank > 1 hits or multi-target questions are evaluated, the metrics diverge mathematically:
    - At rank 2: Recall=1.0, MRR=0.5000, nDCG=0.6309
    - At rank 3: Recall=1.0, MRR=0.3333, nDCG=0.5000
    - Multi-target partial: Recall can be 0.50 while MRR is 1.0.
    """
    single_target = [{"document": "doc-target", "char_start": 50, "char_end": 250}]

    # Demonstration of the identity condition
    rank_1_chunks = [
        ScoredChunk(id="c1", document_id="doc-target", content="text", char_start=50, char_end=250, final_score=0.95),
        ScoredChunk(id="c2", document_id="doc-other", content="text", char_start=0, char_end=100, final_score=0.40)
    ]
    m_identity = evaluator.evaluate_spans(rank_1_chunks, single_target, k=5)
    # The old metrics were identical because of this mathematical identity:
    assert m_identity["recall_at_k"] == m_identity["mrr"] == m_identity["ndcg_at_k"] == 1.0

    # Demonstration of divergence with rank 2 hit
    rank_2_chunks = [
        ScoredChunk(id="c1", document_id="doc-other", content="text", char_start=0, char_end=100, final_score=0.95),
        ScoredChunk(id="c2", document_id="doc-target", content="text", char_start=50, char_end=250, final_score=0.85)
    ]
    m_diverge = evaluator.evaluate_spans(rank_2_chunks, single_target, k=5)
    assert m_diverge["recall_at_k"] == 1.0
    assert m_diverge["mrr"] == 0.5
    assert m_diverge["ndcg_at_k"] == 0.6309
    # Proves they are NOT identical once rank > 1 occurs
    assert m_diverge["recall_at_k"] != m_diverge["mrr"]
    assert m_diverge["mrr"] != m_diverge["ndcg_at_k"]
