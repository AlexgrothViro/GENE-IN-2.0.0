"""Compare candidate parameter sets against canonical baseline."""

from __future__ import annotations

from typing import Any

from .fragment_analysis import bucket_from_result

FINE_BUCKETS = ("20-29", "30-39", "40-49", "50-99", "100+")


def _recovery_for_targets(rows: list[dict[str, Any]]) -> float:
    targets = [row for row in rows if row.get("ground_truth") == "TARGET_VIRUS"]
    if not targets:
        return 0.0
    return round(100.0 * sum(1 for row in targets if row.get("recovered")) / len(targets), 2)


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    short = [
        row
        for row in rows
        if row.get("expected_length_bp") is not None and 20 <= int(row["expected_length_bp"]) <= 49
    ]
    by_bucket: dict[str, float | None] = {}
    for bucket in FINE_BUCKETS:
        bucket_targets = [
            row
            for row in rows
            if bucket_from_result(row) == bucket and row.get("ground_truth") == "TARGET_VIRUS"
        ]
        by_bucket[bucket] = (
            round(100.0 * sum(1 for row in bucket_targets if row.get("recovered")) / len(bucket_targets), 2)
            if bucket_targets
            else None
        )
    runtimes = [float(row["runtime_seconds"]) for row in rows if row.get("runtime_seconds") is not None]
    return {
        "recovery_total_pct": _recovery_for_targets(rows),
        "recovery_20_49_pct": _recovery_for_targets(short),
        "recovery_by_bucket": by_bucket,
        "false_positives": sum(1 for row in rows if row.get("false_positive")),
        "false_negatives": sum(1 for row in rows if row.get("false_negative")),
        "mean_runtime_seconds": round(sum(runtimes) / len(runtimes), 3) if runtimes else 0.0,
        "stages_reused_events": sum(1 for row in rows if (row.get("extra") or {}).get("stages_reused")),
    }


def compare_to_baseline(
    *,
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    baseline_parameter_set_id: str,
    candidate_parameter_set_id: str,
    candidate_parameters: dict[str, Any],
    baseline_parameters: dict[str, Any],
) -> dict[str, Any]:
    base = _aggregate(baseline_rows)
    cand = _aggregate(candidate_rows)
    param_diff = [
        {"parameter": key, "baseline": baseline_parameters.get(key), "candidate": candidate_parameters.get(key)}
        for key in sorted(set(baseline_parameters) | set(candidate_parameters))
        if baseline_parameters.get(key) != candidate_parameters.get(key)
    ]
    return {
        "schema_version": "validation-baseline-compare-v1",
        "baseline_parameter_set_id": baseline_parameter_set_id,
        "candidate_parameter_set_id": candidate_parameter_set_id,
        "parameter_diff": param_diff,
        "baseline": base,
        "candidate": cand,
        "delta": {
            "recovery_total_pct": round(cand["recovery_total_pct"] - base["recovery_total_pct"], 2),
            "recovery_20_49_pct": round(cand["recovery_20_49_pct"] - base["recovery_20_49_pct"], 2),
            "recovery_by_bucket": {
                bucket: (
                    None
                    if cand["recovery_by_bucket"].get(bucket) is None or base["recovery_by_bucket"].get(bucket) is None
                    else round(cand["recovery_by_bucket"][bucket] - base["recovery_by_bucket"][bucket], 2)
                )
                for bucket in FINE_BUCKETS
            },
            "false_positives": cand["false_positives"] - base["false_positives"],
            "false_negatives": cand["false_negatives"] - base["false_negatives"],
            "mean_runtime_seconds": round(cand["mean_runtime_seconds"] - base["mean_runtime_seconds"], 3),
            "stages_reused_events": cand["stages_reused_events"] - base["stages_reused_events"],
        },
    }
