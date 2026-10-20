"""Scientific optimization orchestration (contract + pipeline levels)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .baseline_compare import compare_to_baseline
from .experimental_policy import baseline_thresholds
from .fragment_analysis import analyze_by_bucket
from .optimization_contract import run_contract_optimization
from .optimization_pipeline import run_pipeline_optimization
from .parameter_set import materialize_parameter_set, write_json_atomic
from .pipeline_metrics import build_pipeline_metrics
from .proposal import build_proposal
from .ranking import aggregate_scores, ranking_report

MAX_PIPELINE_PARAMETER_SETS = 5
DEFAULT_PINNED_SETS = Path(__file__).resolve().parents[3] / "config" / "experimental" / "validation" / "pipeline_round4_parameter_sets.json"


def git_head(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def baseline_parameters(repo_root: Path) -> dict[str, Any]:
    thresholds = baseline_thresholds(repo_root)
    return {
        "blast.short_max_bp": thresholds["blast"]["short_max_bp"],
        "blast.dual_mode_min_bp": thresholds["blast"]["dual_mode_min_bp"],
        "blast.dual_mode_max_bp": thresholds["blast"]["dual_mode_max_bp"],
        "locus.minimum_candidate_bp": thresholds["locus"]["minimum_candidate_bp"],
        "locus.gap_bp": thresholds["locus"]["gap_bp"],
        "specificity.minimum_delta_bitscore": thresholds["specificity"]["minimum_delta_bitscore"],
        "specificity.maximum_qcov_difference_pp": thresholds["specificity"]["maximum_qcov_difference_pp"],
        "support.minimum_unique_templates": thresholds["support"]["minimum_unique_templates"],
        "support.minimum_mapq": thresholds["support"]["minimum_mapq"],
    }


def baseline_parameter_set(repo_root: Path, experiment_id: str, out_dir: Path, commit: str) -> dict[str, Any]:
    params = baseline_parameters(repo_root)
    return materialize_parameter_set(
        experiment_id=experiment_id,
        parameters=params,
        out_dir=out_dir,
        baseline_commit=commit,
        grid_id="baseline-canonical",
    )


def materialize_from_overrides(
    *,
    repo_root: Path,
    overrides: dict[str, Any],
    out_dir: Path,
    experiment_id: str,
    commit: str,
    grid_id: str,
) -> dict[str, Any]:
    parameters = dict(baseline_parameters(repo_root))
    parameters.update(overrides)
    return materialize_parameter_set(
        experiment_id=experiment_id,
        parameters=parameters,
        out_dir=out_dir,
        baseline_commit=commit,
        grid_id=grid_id,
    )


def load_pinned_parameter_sets(
    *,
    repo_root: Path,
    pinned_path: Path,
    out_dir: Path,
    experiment_id: str,
    commit: str,
) -> list[dict[str, Any]]:
    payload = json.loads(pinned_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload.get("sets") or []:
        record = materialize_from_overrides(
            repo_root=repo_root,
            overrides=item.get("overrides") or {},
            out_dir=out_dir,
            experiment_id=experiment_id,
            commit=commit,
            grid_id=str(payload.get("round_id") or pinned_path.stem),
        )
        record["selection_role"] = item.get("role")
        if record["parameter_set_id"] not in seen:
            seen.add(record["parameter_set_id"])
            records.append(record)
    return records


def select_parameter_sets_for_pipeline(
    *,
    repo_root: Path,
    ranking: dict[str, Any],
    out_dir: Path,
    experiment_id: str,
    commit: str,
    top_n: int = 5,
    pinned_path: Path | None = None,
) -> list[dict[str, Any]]:
    if pinned_path is not None:
        return load_pinned_parameter_sets(
            repo_root=repo_root,
            pinned_path=pinned_path,
            out_dir=out_dir,
            experiment_id=experiment_id,
            commit=commit,
        )
    cap = min(MAX_PIPELINE_PARAMETER_SETS, max(1, top_n))
    selected_ids: list[str] = []
    baseline = baseline_parameter_set(repo_root, experiment_id, out_dir, commit)
    selected_ids.append(baseline["parameter_set_id"])
    label_priority = (
        "BEST_SHORT_FRAGMENT_RECOVERY",
        "BEST_RECOVERY",
        "BEST_BALANCE",
        "BEST_SPECIFICITY",
    )
    for label in label_priority:
        if len(selected_ids) >= cap:
            break
        for item in ranking.get("configurations") or []:
            if label in item.get("labels", []) and item["parameter_set_id"] not in selected_ids:
                selected_ids.append(item["parameter_set_id"])
                break
    for item in ranking.get("configurations") or []:
        if len(selected_ids) >= cap:
            break
        if item["parameter_set_id"] not in selected_ids:
            selected_ids.append(item["parameter_set_id"])
    records: list[dict[str, Any]] = [baseline]
    for ps_id in selected_ids:
        if ps_id == baseline["parameter_set_id"]:
            continue
        path = out_dir / "parameter_sets" / f"{ps_id}.json"
        if path.is_file():
            records.append(json.loads(path.read_text(encoding="utf-8")))
    deduped = {item["parameter_set_id"]: item for item in records}
    capped = []
    for ps_id in selected_ids:
        record = deduped.get(ps_id)
        if record is not None:
            capped.append(record)
        if len(capped) >= cap:
            break
    return capped


def finalize_contract_outputs(
    *,
    repo_root: Path,
    out_dir: Path,
    manifest: dict[str, Any],
) -> None:
    results = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    ranking = ranking_report(aggregate_scores(results))
    write_json_atomic(out_dir / "ranking.json", ranking)
    write_json_atomic(out_dir / "fragment_analysis.json", analyze_by_bucket(results))
    if ranking.get("configurations"):
        top = ranking["configurations"][0]
        candidate_path = out_dir / "parameter_sets" / f"{top['parameter_set_id']}.json"
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))["parameters"]
        proposal = build_proposal(
            baseline_parameters=baseline_parameters(repo_root),
            candidate_parameters=candidate,
            ranking_entry=top,
            sample_count=len(results),
        )
        write_json_atomic(out_dir / "promotion_proposal.json", proposal)
    baseline_id = baseline_parameter_set(
        repo_root, manifest["experiment_id"], out_dir, manifest["commit"]
    )["parameter_set_id"]
    baseline_rows = [row for row in results if row["parameter_set_id"] == baseline_id]
    comparisons = []
    for ps_id in {row["parameter_set_id"] for row in results}:
        if ps_id == baseline_id:
            continue
        candidate_rows = [row for row in results if row["parameter_set_id"] == ps_id]
        params = json.loads((out_dir / "parameter_sets" / f"{ps_id}.json").read_text(encoding="utf-8"))["parameters"]
        comparisons.append(
            compare_to_baseline(
                baseline_rows=baseline_rows,
                candidate_rows=candidate_rows,
                baseline_parameter_set_id=baseline_id,
                candidate_parameter_set_id=ps_id,
                candidate_parameters=params,
                baseline_parameters=baseline_parameters(repo_root),
            )
        )
    write_json_atomic(out_dir / "baseline_comparison.json", {"comparisons": comparisons})


def run_optimization(
    *,
    repo_root: Path,
    grid_path: Path,
    panel_path: Path,
    pipeline_panel_path: Path,
    out_dir: Path,
    experiment_id: str,
    optimization_level: str,
    top_n: int,
    pinned_parameter_sets: Path | None = None,
) -> dict[str, Any]:
    commit = git_head(repo_root)
    contract_dir = out_dir / "contract" if optimization_level in {"pipeline", "both"} else out_dir
    pipeline_dir = out_dir / "pipeline" if optimization_level in {"pipeline", "both"} else out_dir

    if optimization_level in {"contract", "pipeline", "both"}:
        contract_dir.mkdir(parents=True, exist_ok=True)
        ranking_path = contract_dir / "ranking.json"
        if optimization_level == "contract" or not ranking_path.is_file():
            manifest = run_contract_optimization(
                repo_root=repo_root,
                grid_path=grid_path,
                panel_path=panel_path,
                out_dir=contract_dir,
                experiment_id=experiment_id,
                commit=commit,
            )
            finalize_contract_outputs(repo_root=repo_root, out_dir=contract_dir, manifest=manifest)
        else:
            manifest = json.loads((contract_dir / "manifest.json").read_text(encoding="utf-8"))

    if optimization_level == "contract":
        return manifest

    pipeline_dir.mkdir(parents=True, exist_ok=True)
    ranking = json.loads((contract_dir / "ranking.json").read_text(encoding="utf-8"))
    parameter_sets = select_parameter_sets_for_pipeline(
        repo_root=repo_root,
        ranking=ranking,
        out_dir=contract_dir,
        experiment_id=experiment_id,
        commit=commit,
        top_n=top_n,
        pinned_path=pinned_parameter_sets,
    )
    pipeline_manifest = run_pipeline_optimization(
        repo_root=repo_root,
        panel_path=pipeline_panel_path,
        out_dir=pipeline_dir,
        experiment_id=experiment_id,
        commit=commit,
        parameter_sets=parameter_sets,
    )
    pipeline_results = json.loads((pipeline_dir / "results.json").read_text(encoding="utf-8"))
    write_json_atomic(pipeline_dir / "fragment_analysis.json", analyze_by_bucket(pipeline_results))
    baseline_id = baseline_parameter_set(repo_root, experiment_id, contract_dir, commit)["parameter_set_id"]
    write_json_atomic(
        pipeline_dir / "pipeline_metrics.json",
        build_pipeline_metrics(
            results=pipeline_results,
            parameter_sets=parameter_sets,
            baseline_parameter_set_id=baseline_id,
            baseline_parameters=baseline_parameters(repo_root),
        ),
    )
    write_json_atomic(
        pipeline_dir / "ranking.json",
        ranking_report(aggregate_scores(pipeline_results)),
    )
    write_json_atomic(
        pipeline_dir / "selected_parameter_sets.json",
        {
            "parameter_sets": [item["parameter_set_id"] for item in parameter_sets],
            "pinned": pinned_parameter_sets is not None,
            "selection_cap": MAX_PIPELINE_PARAMETER_SETS,
        },
    )
    return pipeline_manifest
