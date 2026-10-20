"""optimization-pipeline: real Gene-In Evidence execution with stage reuse."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "scripts" / "evidence"

from .experimental_policy import baseline_thresholds, materialize_experimental_policy
from .parameter_map import BLAST_PARAM_KEYS, STAGE_ORDER
from .panel_queries import construction_catalog, sequence_for_entry, write_labels, write_pipeline_panel_fasta, write_query_fasta
from .results import ExperimentResult, write_results_csv, write_results_json
from .runtime import PIPELINE_TOOLS, ensure_genein_bundle_path, which_missing
from .stage_cache import cache_dir, cache_key, reuse_or_copy, save_manifest


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


def required_tools() -> list[str]:
    return list(PIPELINE_TOOLS)


def missing_tools() -> list[str]:
    ensure_genein_bundle_path()
    return which_missing(required_tools())


def _blast_stage_key(sample_id: str, parameters: dict[str, Any]) -> str:
    return cache_key(sample_id, "blast", *(str(parameters.get(key)) for key in BLAST_PARAM_KEYS))


def cached_blast_run(out_dir: Path, sample_id: str, parameters: dict[str, Any]) -> Path | None:
    """Return cached BLAST run dir when blast-affecting parameters match."""
    blast_key = _blast_stage_key(sample_id, parameters)
    cached = cache_dir(out_dir, sample_id, "initial_blast", blast_key) / "run"
    has_blast = (cached / "blastn.tsv").is_file() or (cached / "blastn-short.tsv").is_file()
    if cached.is_dir() and has_blast:
        return cached
    return None


def _store_blast_cache(out_dir: Path, sample_id: str, parameters: dict[str, Any], run_path: Path) -> None:
    blast_key = _blast_stage_key(sample_id, parameters)
    blast_cache = cache_dir(out_dir, sample_id, "initial_blast", blast_key)
    cached_run = blast_cache / "run"
    cached_run.mkdir(parents=True, exist_ok=True)
    stored = []
    for name in ("blastn-short.tsv", "blastn.tsv", "fragment_evidence.tsv", "blast_routing.json"):
        if (run_path / name).is_file():
            reuse_or_copy(run_path / name, cached_run / name)
            stored.append(name)
    save_manifest(
        blast_cache / "manifest.json",
        {
            "stage": "initial_blast",
            "key": blast_key,
            "source_run": str(run_path),
            "parameters": {key: parameters.get(key) for key in BLAST_PARAM_KEYS},
            "artifacts": stored,
        },
    )


def _prepare_panel_assets(work_dir: Path) -> dict[str, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    panel_fa = work_dir / "panel.fa"
    write_pipeline_panel_fasta(panel_fa)
    labels = work_dir / "labels.tsv"
    write_labels(labels)
    catalog_path = work_dir / "construction.json"
    catalog_path.write_text(
        json.dumps(construction_catalog(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    db_prefix = work_dir / "panel_db"
    subprocess.run(
        ["makeblastdb", "-in", str(panel_fa), "-dbtype", "nucl", "-parse_seqids", "-out", str(db_prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
    return {"panel_fa": panel_fa, "labels": labels, "db_prefix": db_prefix}


def _run_evidence_full(
    *,
    repo_root: Path,
    sample_id: str,
    query_fasta: Path,
    evidence_root: Path,
    run_id: str,
    policy_paths: dict[str, Path],
    panel_assets: dict[str, Path],
) -> Path:
    evidence_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        "bash",
        str(repo_root / "scripts/evidence/run.sh"),
        "--sample",
        sample_id,
        "--queries",
        str(query_fasta),
        "--profiles",
        str(policy_paths["profiles"]),
        "--experimental-activation-policy",
        str(policy_paths["activation"]),
        "--evidence-root",
        str(evidence_root),
        "--run-id",
        run_id,
        "--composite-db",
        str(panel_assets["db_prefix"]),
        "--subject-labels",
        str(panel_assets["labels"]),
        "--threads",
        "1",
        "--assembly-method",
        "velvet",
    ]
    subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)
    return evidence_root / "runs" / run_id


def _run_from_cached_blast(
    *,
    repo_root: Path,
    sample_id: str,
    query_fasta: Path,
    run_dir: Path,
    run_id: str,
    policy_paths: dict[str, Path],
    cached_run: Path,
    parameters: dict[str, Any],
) -> list[str]:
    """Rerun competitive + classification using cached BLAST artifacts."""
    if str(EVIDENCE_DIR) not in sys.path:
        sys.path.insert(0, str(EVIDENCE_DIR))
    from config_value import main as config_value_main  # noqa: F401

    stages = [
        "locus_building",
        "hsp_aggregation",
        "competitive_search",
        "evidence_classification",
    ]
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("blastn-short.tsv", "blastn.tsv", "fragment_evidence.tsv", "blast_routing.json"):
        reuse_or_copy(cached_run / name, run_dir / name)
    gap_bp = str(parameters.get("locus.gap_bp") or baseline_thresholds(repo_root)["locus"]["gap_bp"])
    min_delta = str(parameters.get("specificity.minimum_delta_bitscore") or baseline_thresholds(repo_root)["specificity"]["minimum_delta_bitscore"])
    max_qcov = str(parameters.get("specificity.maximum_qcov_difference_pp") or baseline_thresholds(repo_root)["specificity"]["maximum_qcov_difference_pp"])
    subprocess.run(
        [
            sys.executable,
            str(EVIDENCE_DIR / "build_loci.py"),
            "--fragments",
            str(run_dir / "fragment_evidence.tsv"),
            "--gap-bp",
            gap_bp,
            "--out",
            str(run_dir / "locus_evidence.tsv"),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(EVIDENCE_DIR / "build_hsp_evidence.py"),
            "--blast",
            f"blastn-short={run_dir / 'blastn-short.tsv'}",
            "--blast",
            f"blastn={run_dir / 'blastn.tsv'}",
            "--loci",
            str(run_dir / "locus_evidence.tsv"),
            "--out",
            str(run_dir / "hsp_evidence.tsv"),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(EVIDENCE_DIR / "competitive_hits.py"),
            "--fragments",
            str(run_dir / "fragment_evidence.tsv"),
            "--minimum-delta-bitscore",
            min_delta,
            "--maximum-qcov-difference-pp",
            max_qcov,
            "--search-complete",
            "--out",
            str(run_dir / "competitive_hits.tsv"),
        ],
        check=True,
    )
    read_support = run_dir / "read_support.tsv"
    coverage = run_dir / "coverage.tsv"
    if not read_support.is_file():
        read_support.write_text(
            "sample_id\treference_id\tcategory\tlocus_id\torientation\tquery_ids\tlibrary_mode\tumi_mode\tsupport_status\tunique_templates\tdistinct_starts\tproper_pair_templates\tdiscordant_templates\tminimum_mapq\n",
            encoding="utf-8",
        )
    if not coverage.is_file():
        coverage.write_text(
            "reference_id\tcategory\tlocus_id\torientation\tquery_ids\treference_length\tlocus_length\tcovered_bases_1x\tcovered_bases_3x\tbreadth_1x\tbreadth_3x\tmean_depth_locus\tmedian_depth_covered\tmin_depth_covered\tmax_window_depth_fraction\tconcentration_window_bp\tminimum_mapq\tminimum_base_quality\n",
            encoding="utf-8",
        )
    subprocess.run(
        [
            sys.executable,
            str(EVIDENCE_DIR / "classify_sample.py"),
            "--sample",
            sample_id,
            "--loci",
            str(run_dir / "locus_evidence.tsv"),
            "--competitive",
            str(run_dir / "competitive_hits.tsv"),
            "--read-support",
            str(read_support),
            "--coverage",
            str(coverage),
            "--control-status",
            "UNCONTROLLED",
            "--library-mode",
            "shotgun",
            "--experimental-activation-policy",
            str(policy_paths["activation"]),
            "--profiles",
            str(policy_paths["profiles"]),
            "--run-id",
            run_id,
            "--out",
            str(run_dir / "sample_evidence.json"),
        ],
        check=True,
    )
    return stages


def _primary_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer a TARGET_VIRUS LOCUS_CANDIDATE, then the longest remaining candidate."""
    if not candidates:
        return None
    target = [item for item in candidates if item.get("category") == "TARGET_VIRUS"]
    pool = target or list(candidates)
    class_rank = {"LOCUS_CANDIDATE": 2, "EXPLORATORY_FRAGMENT": 1}
    return max(
        pool,
        key=lambda item: (
            class_rank.get(str(item.get("candidate_class")), 0),
            int(item.get("candidate_bp") or 0),
        ),
    )


def _extract_metrics(run_path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "identity_pct": None,
        "adjusted_identity": None,
        "coverage_pct": None,
        "bitscore": None,
        "evalue": None,
        "hsp_count": None,
        "read_support": None,
        "unique_templates": None,
        "target_vs_host_margin": None,
        "target_vs_neighbor_margin": None,
    }
    evidence_path = run_path / "sample_evidence.json"
    if not evidence_path.is_file():
        return metrics
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    metrics["analysis_outcome"] = evidence.get("analysis_outcome")
    metrics["evidence_level"] = evidence.get("evidence_level")
    candidate = _primary_candidate(evidence.get("candidates") or [])
    metrics["classification"] = candidate["candidate_class"] if candidate else "NO_CANDIDATE"
    if candidate:
        metrics["adjusted_identity"] = candidate.get("adj_identity")
        metrics["identity_pct"] = candidate.get("pident")
        metrics["recovered_length_bp"] = candidate.get("candidate_bp")
    frag = run_path / "fragment_evidence.tsv"
    if frag.is_file():
        with frag.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        if rows:
            metrics["bitscore"] = float(rows[0].get("best_bitscore") or 0) or None
            metrics["hsp_count"] = int(rows[0].get("hsp_count") or 0)
    comp = run_path / "competitive_hits.tsv"
    if comp.is_file():
        with comp.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        if rows:
            row = rows[0]
            metrics["target_vs_host_margin"] = row.get("delta_bitscore")
            metrics["competition_outcome"] = row.get("specificity_status")
            host_rows = [item for item in rows if item.get("competitor_category") == "HOST"]
            neighbor_rows = [item for item in rows if item.get("competitor_category") == "NEAR_NON_TARGET_VIRUS"]
            if host_rows:
                metrics["target_vs_host_margin"] = host_rows[0].get("delta_bitscore")
            if neighbor_rows:
                metrics["target_vs_neighbor_margin"] = neighbor_rows[0].get("delta_bitscore")
    category = str(entry.get("category"))
    length = int(entry.get("length_bp"))
    analysis_recovered = metrics.get("analysis_outcome") == "EVIDENCE_RECOVERED"
    # classify_sample only emits TARGET_VIRUS/UNLABELED candidates, so
    # EVIDENCE_RECOVERED on a negative_control is a target-locus false positive.
    recovered = bool(analysis_recovered and category == "TARGET_VIRUS")
    metrics["recovered"] = recovered
    metrics["analysis_recovered"] = analysis_recovered
    metrics["length_bucket"] = _length_bucket(length)
    return metrics


def execute_pipeline_sample(
    *,
    repo_root: Path,
    out_dir: Path,
    entry: dict[str, Any],
    parameters: dict[str, Any],
    parameter_set_id: str,
    experiment_id: str,
    commit: str,
    panel_assets: dict[str, Path],
) -> ExperimentResult:
    started = time.perf_counter()
    sample_id = str(entry["sample_id"])
    category = str(entry["category"])
    length = int(entry["length_bp"])
    role = str(entry.get("sample_role") or "development")
    missing = missing_tools()
    if missing:
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
            status="NOT_EXECUTED",
            technical_failure=True,
            failure_reason=f"Missing tools: {', '.join(missing)}",
            extra={"optimization_level": "pipeline", "missing_tools": missing},
        )
    if length < 20:
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
            status="NOT_EXECUTED",
            technical_failure=True,
            failure_reason="Fragments below 20 bp are not processable by current architecture.",
            extra={"optimization_level": "pipeline", "length_bucket": "<20"},
        )
    work = out_dir / "work" / parameter_set_id / sample_id
    query_fasta = work / "query.fa"
    write_query_fasta(
        query_fasta,
        sample_id,
        category,
        length,
        sequence=sequence_for_entry(entry),
        recipe=str(entry["recipe"]) if entry.get("recipe") else None,
    )
    policy_dir = out_dir / "policy" / parameter_set_id
    policy_paths = materialize_experimental_policy(
        parameters=parameters,
        parameter_set_id=parameter_set_id,
        out_dir=policy_dir,
    )
    run_id = f"validation-{parameter_set_id[-8:]}-{sample_id}"
    evidence_root = out_dir / "evidence" / parameter_set_id
    run_path = evidence_root / "runs" / run_id
    stages_executed: list[str] = []
    stages_reused: list[str] = []
    artifacts_reused: list[dict[str, str]] = []
    cached_run = cached_blast_run(out_dir, sample_id, parameters)
    rerun_from = "locus_building" if cached_run is not None else "initial_blast"
    try:
        if cached_run is not None:
            stages_reused.append("initial_blast")
            stages_executed.extend(
                _run_from_cached_blast(
                    repo_root=repo_root,
                    sample_id=sample_id,
                    query_fasta=query_fasta,
                    run_dir=run_path,
                    run_id=run_id,
                    policy_paths=policy_paths,
                    cached_run=cached_run,
                    parameters=parameters,
                )
            )
            for name in ("blastn-short.tsv", "blastn.tsv", "fragment_evidence.tsv", "blast_routing.json"):
                source = cached_run / name
                if source.is_file():
                    artifacts_reused.append({"artifact": name, "source": str(source)})
        else:
            run_path = _run_evidence_full(
                repo_root=repo_root,
                sample_id=sample_id,
                query_fasta=query_fasta,
                evidence_root=evidence_root,
                run_id=run_id,
                policy_paths=policy_paths,
                panel_assets=panel_assets,
            )
            stages_executed = list(STAGE_ORDER)
            _store_blast_cache(out_dir, sample_id, parameters, run_path)
        metrics = _extract_metrics(run_path, entry)
        minimum_candidate_bp = int(parameters.get("locus.minimum_candidate_bp") or baseline_thresholds(repo_root)["locus"]["minimum_candidate_bp"])
        expected = "NO_TARGET"
        if category == "TARGET_VIRUS":
            expected = "EXPLORATORY_FRAGMENT" if length < minimum_candidate_bp else "LOCUS_CANDIDATE"
        recovered = bool(metrics.get("recovered"))
        observed = metrics.get("classification")
        analysis_recovered = bool(metrics.get("analysis_recovered"))
        concordant = (observed == expected) if category == "TARGET_VIRUS" else not analysis_recovered
        false_positive = role == "negative_control" and analysis_recovered
        false_negative = category == "TARGET_VIRUS" and not recovered
        if false_positive or false_negative:
            status = "REVIEW"
        elif concordant:
            status = "PASS"
        else:
            status = "FAIL"
        return ExperimentResult(
            run_id=run_id,
            experiment_id=experiment_id,
            parameter_set_id=parameter_set_id,
            commit=commit,
            configuration=parameters,
            sample_id=sample_id,
            ground_truth=category,
            sample_role=role,
            expected_length_bp=length,
            recovered_length_bp=metrics.get("recovered_length_bp"),
            identity_pct=float(metrics["identity_pct"]) if metrics.get("identity_pct") not in (None, "") else None,
            coverage_pct=metrics.get("coverage_pct"),
            bitscore=float(metrics["bitscore"]) if metrics.get("bitscore") is not None else None,
            evalue=metrics.get("evalue"),
            evidence_found=recovered,
            recovered=recovered,
            observed_classification=observed,
            expected_classification=expected,
            concordant=concordant,
            false_positive=false_positive,
            false_negative=false_negative,
            competition_outcome=metrics.get("competition_outcome"),
            runtime_seconds=round(time.perf_counter() - started, 3),
            technical_failure=False,
            failure_reason=None,
            status=status,
            extra={
                "optimization_level": "pipeline",
                "length_bucket": metrics.get("length_bucket"),
                "analysis_outcome": metrics.get("analysis_outcome"),
                "evidence_level": metrics.get("evidence_level"),
                "adjusted_identity": metrics.get("adjusted_identity"),
                "hsp_count": metrics.get("hsp_count"),
                "target_vs_host_margin": metrics.get("target_vs_host_margin"),
                "target_vs_neighbor_margin": metrics.get("target_vs_neighbor_margin"),
                "stages_executed": stages_executed,
                "stages_reused": stages_reused,
                "artifacts_reused": artifacts_reused,
                "minimum_rerun_stage": rerun_from,
                "blast_cache_key": _blast_stage_key(sample_id, parameters),
                "read_support": "stubbed_no_fastq",
                "recipe": entry.get("recipe"),
                "design_delta_bitscore": entry.get("design_delta_bitscore"),
                "construction": entry.get("construction"),
            },
        )
    except subprocess.CalledProcessError as exc:
        return ExperimentResult(
            run_id=run_id,
            experiment_id=experiment_id,
            parameter_set_id=parameter_set_id,
            commit=commit,
            configuration=parameters,
            sample_id=sample_id,
            ground_truth=category,
            sample_role=role,
            expected_length_bp=length,
            status="NOT_EXECUTED",
            technical_failure=True,
            failure_reason=(exc.stderr or str(exc))[:500],
            runtime_seconds=round(time.perf_counter() - started, 3),
            extra={"optimization_level": "pipeline", "stages_executed": stages_executed},
        )


def run_pipeline_optimization(
    *,
    repo_root: Path,
    panel_path: Path,
    out_dir: Path,
    experiment_id: str,
    commit: str,
    parameter_sets: list[dict[str, Any]],
) -> dict[str, Any]:
    from .parameter_set import write_json_atomic

    ensure_genein_bundle_path()
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    missing = missing_tools()
    panel_assets: dict[str, Path] | None = None
    if not missing:
        try:
            panel_assets = _prepare_panel_assets(out_dir / "panel_assets")
        except (FileNotFoundError, subprocess.CalledProcessError):
            missing = missing_tools() or ["makeblastdb"]
            panel_assets = None
    results: list[ExperimentResult] = []
    for record in parameter_sets:
        parameters = record["parameters"]
        ps_id = record["parameter_set_id"]
        for entry in panel.get("samples") or []:
            if not entry.get("pipeline_enabled", True):
                continue
            if missing or panel_assets is None:
                results.append(
                    ExperimentResult(
                        run_id=str(uuid.uuid4()),
                        experiment_id=experiment_id,
                        parameter_set_id=ps_id,
                        commit=commit,
                        configuration=parameters,
                        sample_id=str(entry["sample_id"]),
                        ground_truth=str(entry["category"]),
                        sample_role=str(entry.get("sample_role") or "development"),
                        expected_length_bp=int(entry["length_bp"]),
                        status="NOT_EXECUTED",
                        technical_failure=True,
                        failure_reason=f"Missing or unavailable tools: {', '.join(missing)}",
                        extra={"optimization_level": "pipeline", "missing_tools": missing},
                    )
                )
                continue
            results.append(
                execute_pipeline_sample(
                    repo_root=repo_root,
                    out_dir=out_dir,
                    entry=entry,
                    parameters=parameters,
                    parameter_set_id=ps_id,
                    experiment_id=experiment_id,
                    commit=commit,
                    panel_assets=panel_assets,
                )
            )
    write_results_json(out_dir / "results.json", results)
    write_results_csv(out_dir / "results.csv", results)
    manifest = {
        "schema_version": "validation-optimization-run-v1",
        "experiment_id": experiment_id,
        "optimization_level": "pipeline",
        "track": "scientific-optimization",
        "commit": commit,
        "disclaimer": (
            "optimization_level=pipeline reruns Gene-In Evidence stages per "
            "parameter_set on synthetic queries. Upstream BLAST artifacts are "
            "reused only when blast-affecting parameters match, and reuse is "
            "recorded for the configured analysis."
        ),
        "panel_path": str(panel_path.relative_to(repo_root)),
        "parameter_set_count": len(parameter_sets),
        "result_count": len(results),
        "missing_tools": missing_tools(),
        "mode": "ANALYSIS",
    }
    reuse_events = [
        {
            "parameter_set_id": item.parameter_set_id,
            "sample_id": item.sample_id,
            "stages_reused": (item.extra or {}).get("stages_reused") or [],
            "artifacts_reused": (item.extra or {}).get("artifacts_reused") or [],
            "blast_cache_key": (item.extra or {}).get("blast_cache_key"),
        }
        for item in results
        if (item.extra or {}).get("stages_reused")
    ]
    write_json_atomic(out_dir / "reuse_log.json", {"events": reuse_events})
    write_json_atomic(out_dir / "manifest.json", manifest)
    return manifest
