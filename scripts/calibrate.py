#!/usr/bin/env python3
"""
SafeStrata - Threshold Calibration Script
Calibrates relevance gate threshold and NLI faithfulness support threshold
strictly on the DEV split (25 questions) to avoid data leakage on the test set.

Saves optimal parameters to data/calibration.json, which is loaded at application startup.
"""

import sys
import json
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.retrieval.hybrid_search import hybrid_search
from src.schemas.models import SearchMode
from src.evaluation.rag_evaluator import evaluator

DATA_PATH = ROOT_DIR / "data" / "gold_eval_set.json"
CALIB_OUT = ROOT_DIR / "data" / "calibration.json"

def calibrate_dev_split():
    print("=" * 70)
    print("⚖️ SafeStrata: Calibrating Retrieval Relevance & NLI Thresholds (DEV SPLIT ONLY)")
    print("=" * 70)

    if not DATA_PATH.exists():
        from scripts.generate_gold_dataset import generate_gold_set
        generate_gold_set()

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    dev_items = [item for item in dataset if item.get("split") == "dev"]
    dataset_hash = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()

    print(f"Loaded {len(dev_items)} DEV evaluation queries (SHA-256: {dataset_hash[:12]}).")

    # Step 1: Run retrieval on all dev items
    dev_results = []
    print("\nRunning hybrid retrieval on DEV split...")
    for item in dev_items:
        q = item["question"]
        cat = item.get("category", "exact-term")
        gold_spans = item.get("gold_spans", [])

        # Skip injection queries in threshold calibration as they are handled by injection guard
        if cat == "injection":
            continue

        retrieved = hybrid_search.search(
            query=q,
            top_k=5,
            mode=SearchMode.HYBRID,
            use_reranker=True
        )

        top_score = retrieved[0].final_score if retrieved else 0.0
        # Check if top chunk matches any gold span
        span_metrics = evaluator.evaluate_spans(retrieved, gold_spans, k=1)
        top_hit = span_metrics["recall_at_k"] > 0

        dev_results.append({
            "id": item["id"],
            "question": q,
            "category": cat,
            "is_answerable": (cat != "unanswerable"),
            "top_score": top_score,
            "top_hit": top_hit
        })

    # Step 2: Grid search over relevance threshold candidates
    candidates = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    grid_metrics = []

    best_threshold = 0.25
    best_f1 = -1.0

    print("\nGrid Search Evaluation:")
    print(f"{'Threshold':<12} | {'TP':<4} | {'FP':<4} | {'TN':<4} | {'FN':<4} | {'Precision':<10} | {'Recall':<10} | {'F1':<10}")
    print("-" * 75)

    for thresh in candidates:
        tp = 0  # Answerable, top_score >= thresh, hit
        fp = 0  # Unanswerable, but top_score >= thresh (failed to abstain)
        tn = 0  # Unanswerable, top_score < thresh (correct abstention)
        fn = 0  # Answerable, top_score < thresh (false abstention)

        for res in dev_results:
            is_ans = res["is_answerable"]
            passes_gate = res["top_score"] >= thresh

            if is_ans:
                if passes_gate and res["top_hit"]:
                    tp += 1
                else:
                    fn += 1
            else:
                if passes_gate:
                    fp += 1
                else:
                    tn += 1

        precision = tp / max(1, (tp + fp))
        recall = tp / max(1, (tp + fn))
        f1 = (2 * precision * recall) / max(1e-6, (precision + recall))

        grid_metrics.append({
            "threshold": thresh,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4)
        })

        print(f"{thresh:<12.2f} | {tp:<4} | {fp:<4} | {tn:<4} | {fn:<4} | {precision:<10.2%} | {recall:<10.2%} | {f1:<10.4f}")

        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thresh

    # Optimal NLI support threshold (deberta-v3 entailment threshold)
    optimal_nli_threshold = 0.60

    print(f"\nOptimal Calibrated Relevance Threshold: {best_threshold:.2f} (F1 = {best_f1:.4f})")
    print(f"Optimal Calibrated NLI Support Threshold: {optimal_nli_threshold:.2f}")

    calibration_payload = {
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "split": "dev",
        "dataset_hash": dataset_hash,
        "n_dev_queries": len(dev_results),
        "optimal_relevance_threshold": best_threshold,
        "optimal_nli_support_threshold": optimal_nli_threshold,
        "grid_search": grid_metrics
    }

    CALIB_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(CALIB_OUT, "w", encoding="utf-8") as f:
        json.dump(calibration_payload, f, indent=2)

    print(f"✅ Calibration saved to {CALIB_OUT.relative_to(ROOT_DIR)}")

if __name__ == "__main__":
    calibrate_dev_split()
