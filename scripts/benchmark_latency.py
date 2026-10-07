#!/usr/bin/env python3
"""
SafeStrata - Latency Benchmarking Utility
Measures p50, p90, p95, and p99 latency percentiles across query iterations.
"""

import sys
import time
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.hybrid_search import hybrid_search
from src.schemas.models import SearchMode

BENCHMARK_QUERIES = [
    "What is the mathematical definition of Reciprocal Rank Fusion?",
    "How does local Hugging Face SentenceTransformers embedding work?",
    "What are the PII redaction patterns used for enterprise data?",
    "Explain cross-encoder neural reranking vs bi-encoder retrieval.",
    "How does NetworkX model knowledge graph entities and relations?"
]

def benchmark_pipeline(iterations: int = 5):
    print("=" * 75)
    print("⏱️  SafeStrata: Retrieval Latency Benchmark")
    print("=" * 75)
    print(f"Running {iterations} iterations across {len(BENCHMARK_QUERIES)} queries per search mode...\n")

    modes = [
        ("Dense Only (MiniLM-L6-v2)", SearchMode.DENSE, False),
        ("Sparse Only (BM25Okapi)", SearchMode.SPARSE, False),
        ("Hybrid Fusion (RRF)", SearchMode.HYBRID, False),
        ("Hybrid + Neural Reranker", SearchMode.HYBRID, True),
    ]

    for label, mode, use_rerank in modes:
        latencies = []
        for _ in range(iterations):
            for q in BENCHMARK_QUERIES:
                t0 = time.perf_counter()
                hybrid_search.search(query=q, top_k=5, mode=mode, use_reranker=use_rerank)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                latencies.append(elapsed_ms)

        latencies_arr = np.array(latencies)
        p50 = np.percentile(latencies_arr, 50)
        p90 = np.percentile(latencies_arr, 90)
        p95 = np.percentile(latencies_arr, 95)
        p99 = np.percentile(latencies_arr, 99)
        avg = np.mean(latencies_arr)

        print(f"📌 {label}")
        print(f"   Mean: {avg:6.2f}ms | p50: {p50:6.2f}ms | p90: {p90:6.2f}ms | p95: {p95:6.2f}ms | p99: {p99:6.2f}ms")
        print("-" * 75)

    print("=" * 75)
    print("✅ Latency Benchmark Complete!")
    print("=" * 75)

if __name__ == "__main__":
    benchmark_pipeline()
