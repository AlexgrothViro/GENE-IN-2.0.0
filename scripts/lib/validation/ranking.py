"""Aggregate and rank Validation optimization results."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class ConfigScore:
    parameter_set_id: str
    total_samples: int
    recovery_total_pct: float
    recovery_20_49_pct: float
    recovery_by_length: dict[str, float]
    false_positives: int
    false_negatives: int
    negative_control_fp: int
    specific_false_positives: int
    competitive_margin_pass_pct: float
    sample_consistency_pct: float
    repeat_stability_pct: float | None
    mean_runtime_seconds: float | None
    labels: list[str]


def _length_bucket(length: int | None) -> str:
    if length is None:
        return "unknown"
    if 20 <= length <= 49:
        return "20-49"
    if 50 <= length <= 79:
        return "50-79"
    if 80 <= length <= 99:
        return "80-99"
    if length >= 100:
        return "100+"
    return "<20"


def aggregate_scores(results: list[dict[str, Any]]) -> list[ConfigScore]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[str(row["parameter_set_id"])].append(row)

    scores: list[ConfigScore] = []
    for parameter_set_id, rows in grouped.items():
        targets = [row for row in rows if row.get("ground_truth") == "TARGET_VIRUS"]
        recovered = [row for row in targets if row.get("recovered")]
        short = [row for row in targets if _length_bucket(row.get("expected_length_bp")) == "20-49"]
        short_recovered = [row for row in short if row.get("recovered")]
        by_length: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in targets:
            by_length[_length_bucket(row.get("expected_length_bp"))].append(row)
        recovery_by_length = {
            bucket: round(100.0 * sum(1 for item in items if item.get("recovered")) / len(items), 2)
            for bucket, items in sorted(by_length.items())
            if items
        }
        negatives = [row for row in rows if row.get("sample_role") == "negative_control"]
        negative_fp = sum(1 for row in negatives if row.get("false_positive"))
        specific_fp = sum(
            1
            for row in negatives
            if str(row.get("competition_outcome")) == "TARGET_SPECIFIC"
        )
        competitive = [row for row in rows if row.get("competition_outcome")]
        competitive_pass = sum(
            1 for row in competitive if str(row.get("competition_outcome")) == "TARGET_SPECIFIC"
        )
        sample_ids = {str(row.get("sample_id")) for row in rows}
        per_sample: dict[str, list[bool]] = defaultdict(list)
        for row in rows:
            per_sample[str(row.get("sample_id"))].append(bool(row.get("recovered")))
        consistent = sum(1 for values in per_sample.values() if len(set(values)) == 1)
        runtimes = [float(row["runtime_seconds"]) for row in rows if row.get("runtime_seconds") is not None]
        score = ConfigScore(
            parameter_set_id=parameter_set_id,
            total_samples=len(rows),
            recovery_total_pct=round(100.0 * len(recovered) / len(targets), 2) if targets else 0.0,
            recovery_20_49_pct=round(100.0 * len(short_recovered) / len(short), 2) if short else 0.0,
            recovery_by_length=recovery_by_length,
            false_positives=sum(1 for row in rows if row.get("false_positive")),
            false_negatives=sum(1 for row in rows if row.get("false_negative")),
            negative_control_fp=negative_fp,
            specific_false_positives=specific_fp,
            competitive_margin_pass_pct=round(100.0 * competitive_pass / len(competitive), 2)
            if competitive
            else 0.0,
            sample_consistency_pct=round(100.0 * consistent / len(sample_ids), 2) if sample_ids else 0.0,
            repeat_stability_pct=None,
            mean_runtime_seconds=round(sum(runtimes) / len(runtimes), 3) if runtimes else None,
            labels=[],
        )
        scores.append(score)
    return scores


def label_scores(scores: list[ConfigScore]) -> list[ConfigScore]:
    if not scores:
        return scores
    best_recovery = max(
        scores,
        key=lambda item: (
            item.recovery_20_49_pct,
            item.recovery_total_pct,
            -item.false_negatives,
            -item.specific_false_positives,
        ),
    )
    best_short = max(
        scores,
        key=lambda item: (
            item.recovery_by_length.get("20-49", 0.0),
            item.recovery_20_49_pct,
            -item.false_negatives,
        ),
    )
    best_specificity = min(
        scores,
        key=lambda item: (item.specific_false_positives, item.false_positives, item.negative_control_fp),
    )
    best_balance = max(
        scores,
        key=lambda item: (
            item.recovery_20_49_pct - item.false_positives,
            item.recovery_total_pct - item.false_negatives,
        ),
    )
    labeled: list[ConfigScore] = []
    for score in scores:
        labels = list(score.labels)
        if score.parameter_set_id == best_recovery.parameter_set_id:
            labels.append("BEST_RECOVERY")
        if score.parameter_set_id == best_short.parameter_set_id:
            labels.append("BEST_SHORT_FRAGMENT_RECOVERY")
        if score.parameter_set_id == best_specificity.parameter_set_id:
            labels.append("BEST_SPECIFICITY")
        if score.parameter_set_id == best_balance.parameter_set_id:
            labels.append("BEST_BALANCE")
        if not labels:
            labels.append("REVIEW_REQUIRED")
        labeled.append(ConfigScore(**{**score.__dict__, "labels": sorted(set(labels))}))
    return labeled


def ranking_report(scores: list[ConfigScore]) -> dict[str, Any]:
    labeled = label_scores(scores)
    return {
        "schema_version": "validation-ranking-v1",
        "description": "Ranking calculated from the selected optimization results.",
        "configurations": [
            {
                "parameter_set_id": item.parameter_set_id,
                "recovery_20_49_pct": item.recovery_20_49_pct,
                "recovery_total_pct": item.recovery_total_pct,
                "recovery_by_length": item.recovery_by_length,
                "false_positives": item.false_positives,
                "false_negatives": item.false_negatives,
                "negative_control_fp": item.negative_control_fp,
                "specific_false_positives": item.specific_false_positives,
                "competitive_margin_pass_pct": item.competitive_margin_pass_pct,
                "sample_consistency_pct": item.sample_consistency_pct,
                "mean_runtime_seconds": item.mean_runtime_seconds,
                "labels": item.labels,
            }
            for item in sorted(
                labeled,
                key=lambda row: (
                    -row.recovery_20_49_pct,
                    -row.recovery_total_pct,
                    row.false_negatives,
                    row.specific_false_positives,
                    row.false_positives,
                ),
            )
        ],
    }
