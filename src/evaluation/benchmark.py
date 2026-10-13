import os
import json
import time
import subprocess
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

from src.core.config import BASE_DIR
from src.schemas.models import BenchmarkReport, BootstrapCI, SearchMode
from src.evaluation.rag_evaluator import evaluator

def compute_bootstrap_ci(values: List[float], n_bootstraps: int = 1000, ci: float = 0.95) -> BootstrapCI:
    """Computes mean and 95% non-parametric bootstrap confidence interval."""
    if not values:
        return BootstrapCI(mean=0.0, ci_lower=0.0, ci_upper=0.0)
    arr = np.array(values, dtype=np.float64)
    mean_val = float(np.mean(arr))
    if len(arr) == 1 or np.all(arr == arr[0]):
        return BootstrapCI(mean=round(mean_val, 4), ci_lower=round(mean_val, 4), ci_upper=round(mean_val, 4))

    rng = np.random.default_rng(seed=42)
    boot_means = np.empty(n_bootstraps)
    for i in range(n_bootstraps):
        sample = rng.choice(arr, size=len(arr), replace=True)
        boot_means[i] = np.mean(sample)

    alpha = (1.0 - ci) / 2.0
    lower = float(np.percentile(boot_means, alpha * 100))
    upper = float(np.percentile(boot_means, (1.0 - alpha) * 100))
    return BootstrapCI(
        mean=round(mean_val, 4),
        ci_lower=round(lower, 4),
        ci_upper=round(upper, 4)
    )

class BenchmarkRunner:
    """Production evaluation runner executing gold evaluation sets with bootstrap CIs and ablations."""

    def __init__(self, dataset_path: Optional[str] = None):
        self.dataset_path = Path(dataset_path or (BASE_DIR / "data" / "gold_eval_set.json"))

    def load_dataset(self) -> List[Dict[str, Any]]:
        if not self.dataset_path.exists():
            from scripts.generate_gold_dataset import generate_gold_set
            generate_gold_set()
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_git_sha(self) -> str:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=True
            )
            return res.stdout.strip()
        except Exception:
            return "HEAD"

    def run_benchmark(self, split: str = "test") -> BenchmarkReport:
        dataset = self.load_dataset()
        dataset_bytes = self.dataset_path.read_bytes()
        dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()

        test_items = [item for item in dataset if item.get("split") == split]
        if not test_items:
            test_items = dataset

        # Warm-up phase (5 queries excluded from latency benchmarks)
        for warm_item in test_items[:min(5, len(test_items))]:
            evaluator.evaluate_single(warm_item, search_mode=SearchMode.HYBRID, use_reranker=True, skip_generation=True)

        # Primary architecture: Hybrid + Neural Cross-Encoder Reranker
        latencies: List[float] = []
        recalls: List[float] = []
        mrrs: List[float] = []
        ndcgs: List[float] = []
        faithfulnesses: List[float] = []
        relevances: List[float] = []

        for item in test_items:
            res = evaluator.evaluate_single(item, search_mode=SearchMode.HYBRID, use_reranker=True, use_hyde=False)
            recalls.append(res.recall_at_k)
            mrrs.append(res.mrr)
            ndcgs.append(res.ndcg_at_k)
            faithfulnesses.append(res.faithfulness)
            relevances.append(res.answer_relevance)
            latencies.append(res.latency_ms)

        latency_arr = np.array(latencies, dtype=np.float64)
        latency_p50 = float(np.percentile(latency_arr, 50))
        latency_p95 = float(np.percentile(latency_arr, 95))

        metrics_summary = {
            "recall_at_k": compute_bootstrap_ci(recalls),
            "mrr": compute_bootstrap_ci(mrrs),
            "ndcg_at_k": compute_bootstrap_ci(ndcgs),
            "claim_entailment_faithfulness": compute_bootstrap_ci(faithfulnesses),
            "embedding_similarity_relevance": compute_bootstrap_ci(relevances)
        }

        # Ablation experiments across configurations
        ablation_configs = {
            "dense_only": (SearchMode.DENSE, False, False),
            "sparse_bm25_only": (SearchMode.SPARSE, False, False),
            "hybrid_rrf": (SearchMode.HYBRID, False, False),
            "hybrid_reranker": (SearchMode.HYBRID, True, False),
            "hybrid_reranker_hyde": (SearchMode.HYBRID, True, True),
        }

        ablations_summary: Dict[str, Dict[str, BootstrapCI]] = {}
        for ab_name, (mode, use_rr, use_hy) in ablation_configs.items():
            ab_recalls = []
            ab_mrrs = []
            ab_ndcgs = []
            ab_faiths = []
            ab_relevs = []
            for item in test_items:
                res = evaluator.evaluate_single(item, search_mode=mode, use_reranker=use_rr, use_hyde=use_hy, skip_generation=True)
                ab_recalls.append(res.recall_at_k)
                ab_mrrs.append(res.mrr)
                ab_ndcgs.append(res.ndcg_at_k)
                ab_faiths.append(res.faithfulness)
                ab_relevs.append(res.answer_relevance)

            ablations_summary[ab_name] = {
                "recall_at_k": compute_bootstrap_ci(ab_recalls),
                "mrr": compute_bootstrap_ci(ab_mrrs),
                "ndcg_at_k": compute_bootstrap_ci(ab_ndcgs),
                "faithfulness": compute_bootstrap_ci(ab_faiths),
                "relevance": compute_bootstrap_ci(ab_relevs)
            }

        return BenchmarkReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            git_sha=self.get_git_sha(),
            dataset_hash=dataset_hash,
            dataset_size=len(dataset),
            test_size=len(test_items),
            metrics=metrics_summary,
            latency={
                "p50_ms": round(latency_p50, 2),
                "p95_ms": round(latency_p95, 2)
            },
            ablations=ablations_summary
        )

benchmark_runner = BenchmarkRunner()
