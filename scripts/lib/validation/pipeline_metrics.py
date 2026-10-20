"""Per-parameter-set pipeline metrics for Validation optimization-pipeline rounds."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .baseline_compare import compare_to_baseline
from .fragment_analysis import BUCKETS, bucket_from_result


FINE_BUCKETS = ("20-29", "30-39", "40-49", "50-99", "100+")
BOUNDARY_PAIRS = (("pipe_target_39bp", "pipe_target_40bp"), ("pipe_target_49bp", "pipe_target_50bp"))
DELTA_DESIGN_SAMPLES = (
    "pipe_compete_host_1mm_49bp",
    "pipe_compete_host_1mm_50bp",
    "pipe_compete_host_2mm_50bp",
    "pipe_compete_neigh_3mm_50bp",
    "pipe_compete_neigh_4mm_50bp",
)
ROUTING_SAMPLES = ("pipe_route_short_only_49bp",)
SPECIFIC_FP_SAMPLES = ("pipe_fp_delta_mid_50bp",)


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _extra(row: dict[str, Any]) -> dict[str, Any]:
    extra = row.get("extra") or {}
    return extra if isinstance(extra, dict) else {}


def _target_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("ground_truth") == "TARGET_VIRUS"]


def _short_target_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in _target_rows(rows)
        if row.get("expected_length_bp") is not None and 20 <= int(row["expected_length_bp"]) <= 49
    ]


def _analysis_recovered(row: dict[str, Any]) -> bool:
    outcome = _extra(row).get("analysis_outcome")
    if outcome:
        return str(outcome) == "EVIDENCE_RECOVERED"
    if row.get("sample_role") == "negative_control":
        return bool(row.get("false_positive"))
    return bool(row.get("recovered"))


def _recovery_pct(target_rows: list[dict[str, Any]]) -> float:
    if not target_rows:
        return 0.0
    return round(100.0 * sum(1 for row in target_rows if row.get("recovered")) / len(target_rows), 2)


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targets = _target_rows(rows)
    recovered = [row for row in targets if row.get("recovered")]
    host_margins = [
        value
        for row in rows
        if (value := _as_float(_extra(row).get("target_vs_host_margin"))) is not None
    ]
    neighbor_margins = [
        value
        for row in rows
        if (value := _as_float(_extra(row).get("target_vs_neighbor_margin"))) is not None
    ]
    runtimes = [float(row["runtime_seconds"]) for row in rows if row.get("runtime_seconds") is not None]
    reused_events = sum(1 for row in rows if _extra(row).get("stages_reused"))
    stage_counts: Counter[str] = Counter()
    for row in rows:
        for stage in _extra(row).get("stages_reused") or []:
            stage_counts[str(stage)] += 1
    outcomes = Counter(str(row.get("competition_outcome") or "NONE") for row in rows)
    by_bucket: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[bucket_from_result(row)].append(row)
    for bucket in FINE_BUCKETS:
        bucket_rows = grouped.get(bucket) or []
        if not bucket_rows:
            continue
        bucket_targets = _target_rows(bucket_rows)
        by_bucket[bucket] = {
            "samples": len(bucket_rows),
            "target_samples": len(bucket_targets),
            "recovery_pct": round(
                100.0 * sum(1 for row in bucket_targets if row.get("recovered")) / len(bucket_targets), 2
            )
            if bucket_targets
            else None,
            "false_positives": sum(1 for row in bucket_rows if row.get("false_positive")),
            "false_negatives": sum(1 for row in bucket_rows if row.get("false_negative")),
            "competition_outcome": dict(Counter(str(row.get("competition_outcome") or "NONE") for row in bucket_rows)),
            "mean_target_vs_host_margin": _mean(
                [
                    value
                    for row in bucket_rows
                    if (value := _as_float(_extra(row).get("target_vs_host_margin"))) is not None
                ]
            ),
            "mean_target_vs_neighbor_margin": _mean(
                [
                    value
                    for row in bucket_rows
                    if (value := _as_float(_extra(row).get("target_vs_neighbor_margin"))) is not None
                ]
            ),
            "mean_runtime_seconds": _mean(
                [float(row["runtime_seconds"]) for row in bucket_rows if row.get("runtime_seconds") is not None]
            ),
            "stages_reused_events": sum(1 for row in bucket_rows if _extra(row).get("stages_reused")),
        }
    short_targets = _short_target_rows(rows)
    negatives = [row for row in rows if row.get("sample_role") == "negative_control"]
    routing_rows = [row for row in targets if str(row.get("sample_id")) in ROUTING_SAMPLES]
    routing_fn = sum(1 for row in routing_rows if not _analysis_recovered(row))
    classification_fn = sum(
        1
        for row in targets
        if row.get("false_negative") and str(row.get("sample_id")) not in ROUTING_SAMPLES
    )
    intermediate_fp = sum(
        1
        for row in negatives
        if _analysis_recovered(row) and str(row.get("competition_outcome")) != "TARGET_SPECIFIC"
    )
    specific_fp = sum(
        1
        for row in negatives
        if str(row.get("competition_outcome")) == "TARGET_SPECIFIC"
    )
    ambiguous_recovered_targets = sum(
        1
        for row in targets
        if row.get("recovered") and str(row.get("competition_outcome")) == "AMBIGUOUS"
    )
    return {
        "total_samples": len(rows),
        "target_samples": len(targets),
        "recovery_total_pct": _recovery_pct(targets),
        "recovery_20_49_pct": _recovery_pct(short_targets),
        "recovery_by_bucket": by_bucket,
        "false_positives": sum(1 for row in rows if row.get("false_positive")),
        "false_negatives": sum(1 for row in rows if row.get("false_negative")),
        "routing_false_negatives": routing_fn,
        "classification_false_negatives": classification_fn,
        "intermediate_false_positives": intermediate_fp,
        "specific_false_positives": specific_fp,
        "ambiguous_recovered_targets": ambiguous_recovered_targets,
        "competition_outcome": dict(outcomes),
        "mean_target_vs_host_margin": _mean(host_margins),
        "mean_target_vs_neighbor_margin": _mean(neighbor_margins),
        "mean_runtime_seconds": _mean(runtimes),
        "stages_reused_events": reused_events,
        "stages_reused": dict(stage_counts),
        "technical_failures": sum(1 for row in rows if row.get("technical_failure")),
        "status_counts": dict(Counter(str(row.get("status") or "UNKNOWN") for row in rows)),
    }


def _sample_slice(rows: list[dict[str, Any]], sample_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    wanted = set(sample_ids)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = str(row.get("sample_id"))
        if sample_id not in wanted:
            continue
        out[sample_id] = {
            "recovered": bool(row.get("recovered")),
            "false_positive": bool(row.get("false_positive")),
            "false_negative": bool(row.get("false_negative")),
            "competition_outcome": row.get("competition_outcome"),
            "observed_classification": row.get("observed_classification"),
            "expected_classification": row.get("expected_classification"),
            "target_vs_host_margin": _as_float(_extra(row).get("target_vs_host_margin")),
            "target_vs_neighbor_margin": _as_float(_extra(row).get("target_vs_neighbor_margin")),
            "stages_reused": list(_extra(row).get("stages_reused") or []),
            "status": row.get("status"),
        }
    return out


def summarize_parameter_set(
    rows: list[dict[str, Any]],
    *,
    parameter_set_id: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = summarize_rows(rows)
    summary["parameter_set_id"] = parameter_set_id
    summary["parameters"] = parameters or {}
    summary["boundaries"] = {
        "39_vs_40": _sample_slice(rows, BOUNDARY_PAIRS[0]),
        "49_vs_50": _sample_slice(rows, BOUNDARY_PAIRS[1]),
        "delta_designed": _sample_slice(rows, DELTA_DESIGN_SAMPLES),
        "routing_49bp": _sample_slice(rows, ROUTING_SAMPLES),
        "specific_fp_decoy": _sample_slice(rows, SPECIFIC_FP_SAMPLES),
    }
    return summary


def configs_that_differ(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify fixtures whose outcomes are not identical across parameter sets."""
    by_sample: dict[str, dict[str, str]] = defaultdict(dict)
    for row in results:
        sample_id = str(row.get("sample_id"))
        ps_id = str(row.get("parameter_set_id"))
        key = (
            f"rec={bool(row.get('recovered'))}|fp={bool(row.get('false_positive'))}|"
            f"fn={bool(row.get('false_negative'))}|co={row.get('competition_outcome')}|"
            f"cls={row.get('observed_classification')}"
        )
        by_sample[sample_id][ps_id] = key
    discriminating = sorted(
        sample_id for sample_id, per_ps in by_sample.items() if len(set(per_ps.values())) > 1
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[str(row["parameter_set_id"])].append(row)
    summaries = [summarize_rows(rows) for rows in grouped.values()]
    if len(summaries) < 2:
        return {"discriminating_sample_ids": discriminating, "collapsed_on_recovery_fp_fn_competition": True}
    recovery_values = {item["recovery_total_pct"] for item in summaries}
    fp_values = {item["false_positives"] for item in summaries}
    fn_values = {item["false_negatives"] for item in summaries}
    specific_fp_values = {item["specific_false_positives"] for item in summaries}
    outcome_values = {tuple(sorted(item["competition_outcome"].items())) for item in summaries}
    collapsed = (
        len(recovery_values) == 1
        and len(fp_values) == 1
        and len(fn_values) == 1
        and len(specific_fp_values) == 1
        and len(outcome_values) == 1
    )
    return {
        "discriminating_sample_ids": discriminating,
        "collapsed_on_recovery_fp_fn_competition": collapsed,
        "distinct_recovery_total_pct": sorted(recovery_values),
        "distinct_false_positives": sorted(fp_values),
        "distinct_false_negatives": sorted(fn_values),
        "distinct_specific_false_positives": sorted(specific_fp_values),
    }


def _metric_tuple(summary: dict[str, Any]) -> tuple[float, float, int, int, int, int]:
    return (
        float(summary.get("recovery_20_49_pct") or 0.0),
        float(summary.get("recovery_total_pct") or 0.0),
        -int(summary.get("routing_false_negatives") or 0),
        -int(summary.get("false_negatives") or 0),
        -int(summary.get("specific_false_positives") or 0),
        -int(summary.get("false_positives") or 0),
    )


def detect_early_discard(
    *,
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Flag configs that look better on FP only because targets never reach downstream."""
    baseline_by_sample = {str(row["sample_id"]): row for row in baseline_rows}
    lost_targets = []
    for row in candidate_rows:
        if row.get("ground_truth") != "TARGET_VIRUS":
            continue
        sample_id = str(row["sample_id"])
        base = baseline_by_sample.get(sample_id)
        if base is None:
            continue
        if _analysis_recovered(base) and not _analysis_recovered(row):
            lost_targets.append(
                {
                    "sample_id": sample_id,
                    "length_bp": row.get("expected_length_bp"),
                    "baseline_competition_outcome": base.get("competition_outcome"),
                    "candidate_competition_outcome": row.get("competition_outcome"),
                    "baseline_classification": base.get("observed_classification"),
                    "candidate_classification": row.get("observed_classification"),
                }
            )
    delta_fp = int(candidate_summary.get("false_positives") or 0) - int(baseline_summary.get("false_positives") or 0)
    delta_specific_fp = int(candidate_summary.get("specific_false_positives") or 0) - int(
        baseline_summary.get("specific_false_positives") or 0
    )
    delta_recovery_20_49 = float(candidate_summary.get("recovery_20_49_pct") or 0.0) - float(
        baseline_summary.get("recovery_20_49_pct") or 0.0
    )
    suspicious = (
        delta_recovery_20_49 < 0
        and delta_fp <= 0
        and delta_specific_fp <= 0
        and bool(lost_targets)
    )
    return {
        "suspicious_early_discard": suspicious,
        "lost_target_samples": lost_targets,
        "delta_recovery_20_49_pct": round(delta_recovery_20_49, 2),
        "delta_false_positives": delta_fp,
        "delta_specific_false_positives": delta_specific_fp,
    }


def configs_dominated(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Pareto domination prioritizing short-fragment recovery, then routing/FN, then FP."""
    dominated: list[dict[str, Any]] = []
    undominated: list[str] = []
    for candidate in summaries:
        beaten_by = []
        cand_tuple = _metric_tuple(candidate)
        for other in summaries:
            if other["parameter_set_id"] == candidate["parameter_set_id"]:
                continue
            other_tuple = _metric_tuple(other)
            if other_tuple == cand_tuple:
                continue
            if all(left >= right for left, right in zip(other_tuple, cand_tuple)):
                beaten_by.append(other["parameter_set_id"])
        entry = {
            "parameter_set_id": candidate["parameter_set_id"],
            "dominated_by": beaten_by,
            "recovery_20_49_pct": candidate.get("recovery_20_49_pct"),
            "recovery_total_pct": candidate.get("recovery_total_pct"),
            "routing_false_negatives": candidate.get("routing_false_negatives"),
            "false_negatives": candidate.get("false_negatives"),
            "intermediate_false_positives": candidate.get("intermediate_false_positives"),
            "specific_false_positives": candidate.get("specific_false_positives"),
            "false_positives": candidate.get("false_positives"),
        }
        if beaten_by:
            dominated.append(entry)
        else:
            undominated.append(candidate["parameter_set_id"])
    return {
        "undominated_parameter_set_ids": undominated,
        "dominated": dominated,
        "axes": [
            "recovery_20_49_pct (max)",
            "recovery_total_pct (max)",
            "routing_false_negatives (min)",
            "false_negatives (min)",
            "specific_false_positives (min)",
            "false_positives (min)",
        ],
        "note": (
            "Intermediate AMBIGUOUS on recovered targets is not penalized. "
            "intermediate_false_positives counts recovered negatives that did not reach TARGET_SPECIFIC."
        ),
    }


def build_pipeline_metrics(
    *,
    results: list[dict[str, Any]],
    parameter_sets: list[dict[str, Any]],
    baseline_parameter_set_id: str,
    baseline_parameters: dict[str, Any],
) -> dict[str, Any]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        by_id[str(row["parameter_set_id"])].append(row)
    params_by_id = {item["parameter_set_id"]: item.get("parameters") or {} for item in parameter_sets}
    summaries = [
        summarize_parameter_set(
            by_id.get(ps_id, []),
            parameter_set_id=ps_id,
            parameters=params_by_id.get(ps_id) or {},
        )
        for ps_id in [item["parameter_set_id"] for item in parameter_sets]
        if ps_id in by_id
    ]
    baseline_rows = by_id.get(baseline_parameter_set_id) or []
    baseline_summary = next(
        (item for item in summaries if item["parameter_set_id"] == baseline_parameter_set_id),
        None,
    )
    comparisons = []
    early_discard_flags = []
    for item in parameter_sets:
        ps_id = item["parameter_set_id"]
        if ps_id == baseline_parameter_set_id:
            continue
        candidate_rows = by_id.get(ps_id) or []
        comparisons.append(
            compare_to_baseline(
                baseline_rows=baseline_rows,
                candidate_rows=candidate_rows,
                baseline_parameter_set_id=baseline_parameter_set_id,
                candidate_parameter_set_id=ps_id,
                candidate_parameters=item.get("parameters") or {},
                baseline_parameters=baseline_parameters,
            )
        )
        candidate_summary = next(
            (entry for entry in summaries if entry["parameter_set_id"] == ps_id),
            None,
        )
        if baseline_summary is not None and candidate_summary is not None:
            flag = detect_early_discard(
                baseline_summary=baseline_summary,
                candidate_summary=candidate_summary,
                baseline_rows=baseline_rows,
                candidate_rows=candidate_rows,
            )
            flag["parameter_set_id"] = ps_id
            early_discard_flags.append(flag)
    return {
        "schema_version": "validation-pipeline-metrics-v1",
        "description": "Pipeline metrics calculated from the configured queries.",
        "fine_buckets": list(FINE_BUCKETS),
        "unused_fragment_analysis_buckets": [bucket for bucket in BUCKETS if bucket not in FINE_BUCKETS],
        "parameter_sets": summaries,
        "baseline_comparison": comparisons,
        "discrimination": configs_that_differ(results),
        "domination": configs_dominated(summaries),
        "early_discard_flags": early_discard_flags,
        "early_discard_summary": {
            "count": sum(1 for item in early_discard_flags if item["suspicious_early_discard"]),
            "parameter_set_ids": [
                item["parameter_set_id"]
                for item in early_discard_flags
                if item["suspicious_early_discard"]
            ],
        },
    }
