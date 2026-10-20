"""Fragment length bucket analysis for Validation optimization."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


BUCKETS = ("20-29", "30-39", "40-49", "50-99", "100+", "<20", "unknown")


def bucket_from_result(row: dict[str, Any]) -> str:
    extra = row.get("extra") or {}
    if extra.get("length_bucket"):
        return str(extra["length_bucket"])
    length = row.get("expected_length_bp")
    if length is None:
        return "unknown"
    length = int(length)
    if length < 20:
        return "<20"
    if length <= 29:
        return "20-29"
    if length <= 39:
        return "30-39"
    if length <= 49:
        return "40-49"
    if length <= 99:
        return "50-99"
    return "100+"


def analyze_by_bucket(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[bucket_from_result(row)].append(row)
    summary = {}
    for bucket in BUCKETS:
        rows = grouped.get(bucket) or []
        if not rows:
            continue
        targets = [row for row in rows if row.get("ground_truth") == "TARGET_VIRUS"]
        runtimes = [float(row["runtime_seconds"]) for row in rows if row.get("runtime_seconds") is not None]
        summary[bucket] = {
            "samples": len(rows),
            "target_samples": len(targets),
            "recovery_pct": round(100.0 * sum(1 for row in targets if row.get("recovered")) / len(targets), 2)
            if targets
            else None,
            "false_positives": sum(1 for row in rows if row.get("false_positive")),
            "false_negatives": sum(1 for row in rows if row.get("false_negative")),
            "competition_outcome": dict(Counter(str(row.get("competition_outcome") or "NONE") for row in rows)),
            "mean_runtime_seconds": round(sum(runtimes) / len(runtimes), 3) if runtimes else None,
            "stages_reused_events": sum(1 for row in rows if (row.get("extra") or {}).get("stages_reused")),
            "not_processable": bucket == "<20",
        }
    return {"schema_version": "validation-fragment-analysis-v1", "buckets": summary}
