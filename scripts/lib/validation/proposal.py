"""Parameter-set recommendations produced from optimization results."""

from __future__ import annotations

from typing import Any


def diff_parameters(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    keys = sorted(set(baseline) | set(candidate))
    changes: list[dict[str, Any]] = []
    for key in keys:
        before = baseline.get(key)
        after = candidate.get(key)
        if before != after:
            changes.append({"parameter": key, "baseline": before, "candidate": after})
    return changes


def build_proposal(
    *,
    baseline_parameters: dict[str, Any],
    candidate_parameters: dict[str, Any],
    ranking_entry: dict[str, Any],
    sample_count: int,
) -> dict[str, Any]:
    gains = {
        "recovery_20_49_pct": ranking_entry.get("recovery_20_49_pct"),
        "recovery_total_pct": ranking_entry.get("recovery_total_pct"),
        "competitive_margin_pass_pct": ranking_entry.get("competitive_margin_pass_pct"),
    }
    losses = {
        "false_positives": ranking_entry.get("false_positives"),
        "false_negatives": ranking_entry.get("false_negatives"),
        "negative_control_fp": ranking_entry.get("negative_control_fp"),
    }
    risks = []
    if losses["false_positives"]:
        risks.append("Increased false positives relative to baseline in optimization panel.")
    if losses["negative_control_fp"]:
        risks.append("Negative controls triggered in optimization panel.")
    if sample_count < 20:
        risks.append("Small optimization panel; overfitting risk is high.")
    risks.append("Optimization panel is not independent validation.")
    return {
        "schema_version": "validation-parameter-recommendation-v1",
        "status": "READY",
        "baseline_configuration": baseline_parameters,
        "candidate_configuration": candidate_parameters,
        "parameter_diff": diff_parameters(baseline_parameters, candidate_parameters),
        "quantitative_evidence": ranking_entry,
        "gains": gains,
        "losses": losses,
        "sample_count": sample_count,
        "risks": risks,
        "recommendation": "Use the measured trade-offs to select the desired parameter set.",
    }
