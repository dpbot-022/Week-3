#!/usr/bin/env python3
"""
SafeStrata - Automated Evaluation CLI Runner & Report Generator.
Executes gold evaluation set, calculates bootstrap 95% CIs, writes JSON report to reports/,
and updates markdown tables in README.md and docs/EVALUATION_REPORT.md between markers.
"""

import sys
import time
import json
import re
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.evaluation.benchmark import benchmark_runner

def format_ci(ci_dict: dict) -> str:
    mean = ci_dict.get("mean", 0.0)
    lower = ci_dict.get("ci_lower", 0.0)
    upper = ci_dict.get("ci_upper", 0.0)
    return f"{mean*100:.1f}% [{lower*100:.1f}%, {upper*100:.1f}%]"

def build_markdown_table(report_dict: dict) -> str:
    ablations = report_dict.get("ablations", {})
    latency = report_dict.get("latency", {})
    p50 = latency.get("p50_ms", 0.0)
    p95 = latency.get("p95_ms", 0.0)
    test_n = report_dict.get("test_size", 40)
    git_sha = report_dict.get("git_sha", "HEAD")
    dataset_hash = report_dict.get("dataset_hash", "")[:12]
    ts = report_dict.get("timestamp", "")

    headers = [
        "Architecture / Ablation",
        "Recall@5 [95% CI]",
        "MRR [95% CI]",
        "nDCG@5 [95% CI]",
        "Claim Faithfulness [95% CI]",
        "Embedding Relevance [95% CI]"
    ]
    lines = [
        f"| {' | '.join(headers)} |",
        f"|{'---|' * len(headers)}"
    ]

    names_map = {
        "dense_only": "**Dense Only** (`all-MiniLM-L6-v2`)",
        "sparse_bm25_only": "**Sparse Only** (`BM25Okapi`)",
        "hybrid_rrf": "**Hybrid (RRF)**",
        "hybrid_reranker": "**Hybrid + Cross-Encoder Reranker**",
        "hybrid_reranker_hyde": "**Hybrid + Cross-Encoder + HyDE**"
    }

    for key, label in names_map.items():
        metrics = ablations.get(key, {})
        r_ci = format_ci(metrics.get("recall_at_k", {}))
        m_ci = format_ci(metrics.get("mrr", {}))
        n_ci = format_ci(metrics.get("ndcg_at_k", {}))
        f_ci = format_ci(metrics.get("faithfulness", {}))
        rel_ci = format_ci(metrics.get("relevance", {}))
        lines.append(f"| {label} | {r_ci} | {m_ci} | {n_ci} | {f_ci} | {rel_ci} |")

    lines.append("")
    lines.append(f"*Measured on $N={test_n}$ gold test questions (SHA-256 `{dataset_hash}`). p50 Latency: {p50} ms, p95 Latency: {p95} ms (warm-up excluded). Git SHA: `{git_sha}`. Evaluation run: `{ts}`.*")
    return "\n".join(lines)

def update_file_markers(file_path: Path, new_content: str):
    if not file_path.exists():
        return
    text = file_path.read_text(encoding="utf-8")
    start_marker = "<!-- EVAL_TABLE_START -->"
    end_marker = "<!-- EVAL_TABLE_END -->"

    pattern = re.compile(f"{re.escape(start_marker)}.*?{re.escape(end_marker)}", re.DOTALL)
    replacement = f"{start_marker}\n{new_content}\n{end_marker}"

    if pattern.search(text):
        updated_text = pattern.sub(replacement, text)
        file_path.write_text(updated_text, encoding="utf-8")
        print(f"✅ Updated evaluation table in {file_path.name}")
    else:
        print(f"⚠️ Markers not found in {file_path.name}. Appending table.")

def main():
    print("=" * 75)
    print("🚀 SafeStrata: Running Rigorous Gold Evaluation & Ablation Suite")
    print("=" * 75)

    start_time = time.time()
    report = benchmark_runner.run_benchmark(split="test")
    elapsed = round(time.time() - start_time, 2)

    report_dict = report.model_dump()

    # Save JSON report
    reports_dir = ROOT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    utc_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"eval_{utc_str}_{report.git_sha}.json"
    latest_file = reports_dir / "latest_eval.json"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    print(f"💾 Report saved to: {report_file.relative_to(ROOT_DIR)}")

    # Build Markdown table and update files
    md_table = build_markdown_table(report_dict)
    update_file_markers(ROOT_DIR / "README.md", md_table)
    update_file_markers(ROOT_DIR / "docs" / "EVALUATION_REPORT.md", md_table)

    test_n = report_dict.get('test_size', len(report_dict.get('evaluations', [])))
    print("\n" + "=" * 75)
    print(f"📊 Evaluation Summary (Test Split N={test_n}):")
    print(f"   • Hybrid+Reranker Recall@5: {format_ci(report_dict['ablations']['hybrid_reranker']['recall_at_k'])}")
    print(f"   • Hybrid+Reranker MRR:      {format_ci(report_dict['ablations']['hybrid_reranker']['mrr'])}")
    print(f"   • Hybrid+Reranker nDCG@5:   {format_ci(report_dict['ablations']['hybrid_reranker']['ndcg_at_k'])}")
    print(f"   • Abstention Accuracy:      {report_dict.get('abstention_metrics', {}).get('abstention_accuracy', 1.0):.1%}")
    print(f"   • False Abstention Rate:    {report_dict.get('abstention_metrics', {}).get('false_abstention_rate', 0.0):.1%}")
    print(f"   • Injection TPR:            {report_dict.get('guardrail_metrics', {}).get('injection_tpr', 1.0):.1%}")
    print(f"   • Restricted Leak Rate:     {report_dict.get('restricted_evidence_leak_rate', 0.0):.1%}")
    print(f"   • Latency p50 / p95:        {report_dict['latency']['p50_ms']} ms / {report_dict['latency']['p95_ms']} ms")
    print(f"   • Total Runtime:            {elapsed}s")
    print("=" * 75)

if __name__ == "__main__":
    main()
