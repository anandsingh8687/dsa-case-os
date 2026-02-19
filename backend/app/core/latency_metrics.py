"""In-memory latency metric aggregation for operational monitoring."""

from __future__ import annotations

from collections import deque
from statistics import median
from threading import Lock
from time import time
from typing import Deque, Dict, List


MAX_SAMPLES_PER_KEY = 400

_samples: Dict[str, Deque[float]] = {}
_last_seen: Dict[str, float] = {}
_lock = Lock()


def record_latency(key: str, duration_ms: float) -> None:
    """Store one latency sample for key."""
    if duration_ms < 0:
        return
    with _lock:
        bucket = _samples.setdefault(key, deque(maxlen=MAX_SAMPLES_PER_KEY))
        bucket.append(float(duration_ms))
        _last_seen[key] = time()


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return float(ordered[rank])


def get_latency_snapshot() -> Dict[str, Dict[str, float]]:
    """Return p50/p95 metrics for each key."""
    with _lock:
        snapshot: Dict[str, Dict[str, float]] = {}
        for key, bucket in _samples.items():
            values = list(bucket)
            if not values:
                continue
            snapshot[key] = {
                "count": float(len(values)),
                "p50_ms": round(float(median(values)), 2),
                "p95_ms": round(_percentile(values, 95), 2),
                "max_ms": round(float(max(values)), 2),
                "last_seen_epoch": round(_last_seen.get(key, 0.0), 2),
            }
        return snapshot
