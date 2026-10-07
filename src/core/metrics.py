import time
from typing import Dict, Any
from collections import defaultdict
import threading

class MetricsCollector:
    """Thread-safe in-memory metrics collector for telemetry, queries, and guardrails."""
    def __init__(self):
        self._lock = threading.Lock()
        self.counters = defaultdict(int)
        self.latencies = defaultdict(list)
        self.start_time = time.time()

    def increment(self, metric_name: str, count: int = 1):
        with self._lock:
            self.counters[metric_name] += count

    def record_latency(self, metric_name: str, latency_ms: float):
        with self._lock:
            self.latencies[metric_name].append(latency_ms)
            # Keep max 1000 observations to bound memory
            if len(self.latencies[metric_name]) > 1000:
                self.latencies[metric_name].pop(0)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            summary = {
                "uptime_seconds": round(time.time() - self.start_time, 2),
                "counters": dict(self.counters),
                "latencies_ms": {}
            }
            for name, values in self.latencies.items():
                if values:
                    sorted_vals = sorted(values)
                    n = len(sorted_vals)
                    summary["latencies_ms"][name] = {
                        "count": n,
                        "mean": round(sum(values) / n, 2),
                        "p50": round(sorted_vals[int(n * 0.50)], 2),
                        "p95": round(sorted_vals[min(int(n * 0.95), n - 1)], 2),
                        "p99": round(sorted_vals[min(int(n * 0.99), n - 1)], 2),
                    }
            return summary

metrics = MetricsCollector()
