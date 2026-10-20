"""optimization-contract: fast contract evaluation with experimental policy wiring."""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "scripts" / "evidence"
if str(EVIDENCE_DIR) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_DIR))

from blast_router import profiles_for_length  # noqa: E402
from classify_sample import classify  # noqa: E402
from competitive_hits import evaluate as evaluate_competitive  # noqa: E402

from .experimental_policy import apply_parameters, baseline_thresholds, load_experimental_policy, materialize_experimental_policy
from .parameter_map import contract_active_parameters
from .parameter_set import expand_grid, materialize_parameter_set, write_json_atomic
from .panel_queries import sequence_for_category
from .results import ExperimentResult, write_results_csv, write_results_json


def _length_bucket(length: int | None) -> str:
    if length is None:
        return "unknown"
    if 20 <= length <= 29:
        return "20-29"
    if 30 <= length <= 39:
        return "30-39"
    if 40 <= length <= 49:
        return "40-49"
    if 50 <= length <= 99:
        return "50-99"
    if length >= 100:
        return "100+"
    return "<20"


def _fragment_row(sample_id: str, category: str, length: int, bitscore: float) -> dict[str, str]:
    return {
        "qseqid": sample_id,
        "task": "blastn-short" if length < 50 else "blastn",
        "sseqid": {
            "TARGET_VIRUS": "target_ref",
            "HOST": "host_ref",
            "NEAR_NON_TARGET_VIRUS": "neighbor_ref",
        }.get(category, "contaminant_ref"),
        "category": category,
        "best_bitscore": str(bitscore),
        "query_coverage": "1.0",
        "low_complexity_status": "LOW_COMPLEXITY" if category == "LOW_COMPLEXITY" else "OK",
    }


def _build_competitive_rows(
    sample_id: str,
    category: str,
    length: int,
    thresholds: dict[str, Any],
) -> list[dict[str, str]]:
    if category == "TARGET_VIRUS":
        fragments = [
            _fragment_row(sample_id, "TARGET_VIRUS", length, 80.0),
            _fragment_row(sample_id, "HOST", length, 40.0),
            _fragment_row(sample_id, "NEAR_NON_TARGET_VIRUS", length, 35.0),
        ]
    elif category in {"HOST", "NEAR_NON_TARGET_VIRUS"}:
        fragments = [_fragment_row(sample_id, category, length, 70.0)]
    else:
        return []
    min_delta = float(thresholds["specificity"]["minimum_delta_bitscore"])
    max_qcov = float(thresholds["specificity"]["maximum_qcov_difference_pp"])
    return evaluate_competitive(fragments, min_delta, max_qcov, search_complete=True)


def _build_locus(sample_id: str, category: str, length: int, thresholds: dict[str, Any]) -> dict[str, str]:
    profiles = profiles_for_length(length, thresholds)
    task = profiles[-1] if profiles else "blastn"
    return {
        "locus_id": f"L-{sample_id}",
        "sseqid": "target_ref" if category == "TARGET_VIRUS" else category.lower(),
        "query_ids": sample_id,
        "orientation": "+",
        "task": "blastn-short" if task == "short" else "blastn",
        "category": category,
        "covered_reference_bp": str(length),
        "max_query_length": str(length),
    }


def evaluate_contract_sample(
    *,
    entry: dict[str, Any],
    parameters: dict[str, Any],
    parameter_set_id: str,
    experiment_id: str,
    commit: str,
    policy_paths: dict[str, Path],
    baseline_parameters_map: dict[str, Any],
) -> ExperimentResult:
    started = time.perf_counter()
    sample_id = str(entry["sample_id"])
    category = str(entry["category"])
    length = int(entry["length_bp"])
    role = str(entry.get("sample_role") or "development")
    policy = load_experimental_policy(policy_paths)
    thresholds = policy["thresholds"]
    active = contract_active_parameters(parameters, baseline_parameters_map)
    routing = profiles_for_length(length, thresholds)
    competitive = _build_competitive_rows(sample_id, category, length, thresholds)
    loci = []
    if category == "TARGET_VIRUS":
        loci = [_build_locus(sample_id, category, length, thresholds)]
    elif category in {"HOST", "NEAR_NON_TARGET_VIRUS"}:
        loci = [_build_locus(sample_id, category, length, thresholds)]
    classification = classify(
        sample_id,
        loci,
        competitive,
        [],
        [],
        "UNCONTROLLED",
        "shotgun",
        policy["shadow_mode"],
        policy=policy,
    )
    recovered = classification["analysis_outcome"] == "EVIDENCE_RECOVERED" and bool(loci)
    observed = classification["candidates"][0]["candidate_class"] if classification["candidates"] else "NO_CANDIDATE"
    minimum_candidate_bp = int(thresholds["locus"]["minimum_candidate_bp"])
    expected = "NO_TARGET"
    if category == "TARGET_VIRUS":
        expected = "EXPLORATORY_FRAGMENT" if length < minimum_candidate_bp else "LOCUS_CANDIDATE"
    concordant = (observed == expected) if category == "TARGET_VIRUS" else not recovered
    false_positive = role == "negative_control" and recovered
    false_negative = category == "TARGET_VIRUS" and not recovered
    comp = competitive[0] if competitive else {}
    status = "PASS" if concordant and not false_positive else ("REVIEW" if false_positive else "FAIL")
    return ExperimentResult(
        run_id=str(uuid.uuid4()),
        experiment_id=experiment_id,
        parameter_set_id=parameter_set_id,
        commit=commit,
        configuration=parameters,
        sample_id=sample_id,
        ground_truth=category,
        sample_role=role,
        expected_length_bp=length,
        recovered_length_bp=length if recovered else 0,
        identity_pct=None,
        coverage_pct=None,
        bitscore=float(comp.get("target_bitscore")) if comp.get("target_bitscore") else None,
        evalue=None,
        evidence_found=recovered,
        recovered=recovered,
        observed_classification=observed,
        expected_classification=expected,
        concordant=concordant,
        false_positive=false_positive,
        false_negative=false_negative,
        competition_outcome=str(comp.get("specificity_status")) if comp else None,
        runtime_seconds=round(time.perf_counter() - started, 4),
        technical_failure=False,
        failure_reason=None,
        status=status,
        extra={
            "optimization_level": "contract",
            "not_pipeline_recovery": True,
            "length_bucket": _length_bucket(length),
            "blast_routing": list(routing),
            "contract_active_parameters": active,
            "contract_inactive_parameters": [
                key for key in parameters if key not in active and parameters.get(key) != baseline_parameters_map.get(key)
            ],
            "evidence_level": classification["evidence_level"],
            "analysis_outcome": classification["analysis_outcome"],
        },
    )


def run_contract_optimization(
    *,
    repo_root: Path,
    grid_path: Path,
    panel_path: Path,
    out_dir: Path,
    experiment_id: str,
    commit: str,
) -> dict[str, Any]:
    import json

    grid = json.loads(grid_path.read_text(encoding="utf-8"))
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_map = {
        "blast.short_max_bp": baseline_thresholds(repo_root)["blast"]["short_max_bp"],
        "blast.dual_mode_min_bp": baseline_thresholds(repo_root)["blast"]["dual_mode_min_bp"],
        "blast.dual_mode_max_bp": baseline_thresholds(repo_root)["blast"]["dual_mode_max_bp"],
        "locus.minimum_candidate_bp": baseline_thresholds(repo_root)["locus"]["minimum_candidate_bp"],
        "locus.gap_bp": baseline_thresholds(repo_root)["locus"]["gap_bp"],
        "specificity.minimum_delta_bitscore": baseline_thresholds(repo_root)["specificity"]["minimum_delta_bitscore"],
        "specificity.maximum_qcov_difference_pp": baseline_thresholds(repo_root)["specificity"]["maximum_qcov_difference_pp"],
        "support.minimum_unique_templates": baseline_thresholds(repo_root)["support"]["minimum_unique_templates"],
        "support.minimum_mapq": baseline_thresholds(repo_root)["support"]["minimum_mapq"],
    }
    combinations = expand_grid(grid)
    all_results: list[ExperimentResult] = []
    for parameters in combinations:
        record = materialize_parameter_set(
            experiment_id=experiment_id,
            parameters=parameters,
            out_dir=out_dir,
            baseline_commit=commit,
            grid_id=str(grid.get("grid_id") or grid_path.stem),
        )
        ps_id = record["parameter_set_id"]
        policy_dir = out_dir / "policy" / ps_id
        policy_paths = materialize_experimental_policy(
            parameters=parameters,
            parameter_set_id=ps_id,
            out_dir=policy_dir,
        )
        for entry in panel.get("samples") or []:
            all_results.append(
                evaluate_contract_sample(
                    entry=entry,
                    parameters=parameters,
                    parameter_set_id=ps_id,
                    experiment_id=experiment_id,
                    commit=commit,
                    policy_paths=policy_paths,
                    baseline_parameters_map=baseline_map,
                )
            )
    write_results_json(out_dir / "results.json", all_results)
    write_results_csv(out_dir / "results.csv", all_results)
    manifest = {
        "schema_version": "validation-optimization-run-v1",
        "experiment_id": experiment_id,
        "optimization_level": "contract",
        "track": "scientific-optimization",
        "commit": commit,
        "disclaimer": (
            "optimization_level=contract evaluates experimental policy wiring on "
            "synthetic fixtures. It is not pipeline recovery. An 18-set grid times "
            "an 11-sample development panel yields 198 contract rows; those rows "
            "must not be reported as real Gene-In pipeline recovery."
        ),
        "not_pipeline_recovery": True,
        "grid_path": str(grid_path.relative_to(repo_root)),
        "panel_path": str(panel_path.relative_to(repo_root)),
        "parameter_set_count": len(combinations),
        "result_count": len(all_results),
        "mode": "ANALYSIS",
    }
    write_json_atomic(out_dir / "manifest.json", manifest)
    return manifest
