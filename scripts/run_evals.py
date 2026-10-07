#!/usr/bin/env python3
"""
SafeStrata - Automated AI Evaluation CLI Runner
Executes RAG triad evaluations (Precision, Recall, Faithfulness, Relevance, Latency)
across Dense, Sparse, Hybrid, and Neural Cross-Encoder Reranking pipelines.
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.benchmark import benchmark_runner

def main():
    print("=" * 80)
    print("🧪 SafeStrata: Automated Evaluation & RAG Triad Benchmarking")
    print("=" * 80)
    print("Evaluating 4 retrieval architectures against standardized test queries:\n"
          "  1. Dense Only (Hugging Face all-MiniLM-L6-v2)\n"
          "  2. Sparse Only (BM25Okapi)\n"
          "  3. Hybrid Fusion (Dense + Sparse via RRF)\n"
          "  4. Hybrid + Neural Cross-Encoder Reranker (ms-marco-MiniLM-L-6-v2)\n")

    start = time.time()
    report = benchmark_runner.run_benchmark()
    elapsed = round(time.time() - start, 2)

    print(f"\n📊 Benchmark Execution Completed in {elapsed}s")
    print("-" * 80)
    print(f"{'Retrieval Architecture':<28} | {'Precision':<10} | {'Recall':<8} | {'Faithfulness':<12} | {'Latency':<9}")
    print("-" * 80)

    for arch, metrics in report.aggregate_metrics.items():
        prec = f"{metrics.get('avg_context_precision', 0):.1%}"
        rec = f"{metrics.get('avg_context_recall', 0):.1%}"
        faith = f"{metrics.get('avg_faithfulness', 0):.1%}"
        lat = f"{metrics.get('avg_latency_ms', 0):.1f}ms"
        print(f"{arch:<28} | {prec:<10} | {rec:<8} | {faith:<12} | {lat:<9}")

    print("-" * 80)
    print(f"🏆 Production Recommendation: {report.best_performing_mode}")
    print(f"💡 Architectural Analysis: {report.analysis}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
