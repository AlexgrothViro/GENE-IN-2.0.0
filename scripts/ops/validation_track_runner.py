#!/usr/bin/env python3
"""Orquestrador de análises e testes do Validation."""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from validation.runtime import (
    OPERATIONAL_TOOLS,
    ensure_genein_bundle_path as _ensure_bundle_path,
    genein_bundle_env_bin as _bundle_env_bin,
    which_missing as _which_missing,
)


SCHEMA = "genein-validation-report/v1"
VALID_TRACKS = (
    "engineering",
    "operational",
    "synthetic",
    "competitive",
    "all-safe",
    "scientific-optimization",
    "contract-selftest",
)
DEFAULT_GRID = ROOT / "config" / "experimental" / "validation" / "optimization_grid_v1.json"
DEFAULT_DEV_PANEL = ROOT / "config" / "experimental" / "validation" / "sample_panel_development.json"
DEFAULT_PIPELINE_PANEL = ROOT / "config" / "experimental" / "validation" / "sample_panel_pipeline.json"
DEFAULT_VAL_PANEL = ROOT / "config" / "experimental" / "validation" / "sample_panel_validation_template.json"
DEFAULT_CRITERIA = ROOT / "config" / "experimental" / "validation" / "validation_criteria_template.json"
SAMPLE_ROLES = frozenset({"analytical", "positive_control", "negative_control"})


def repo_root() -> Path:
    return ROOT


def genein_bundle_env_bin(home: Optional[Path] = None) -> Optional[Path]:
    return _bundle_env_bin(home)


def ensure_genein_bundle_path(home: Optional[Path] = None) -> Optional[str]:
    return _ensure_bundle_path(home)


def which_missing(names: Sequence[str]) -> List[str]:
    return _which_missing(names)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_identity(root: Path) -> Dict[str, str]:
    identity = {"commit": "unknown", "branch": "unknown", "dirty": "unknown"}
    git = ["git"]
    if "microsoft" in platform.release().lower() and root.as_posix().startswith("/mnt/"):
        git.extend(["-c", "core.autocrlf=true"])
    try:
        commit = subprocess.run(
            [*git, "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if commit.returncode == 0:
            identity["commit"] = commit.stdout.strip()
        branch = subprocess.run(
            [*git, "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if branch.returncode == 0:
            identity["branch"] = branch.stdout.strip()
        dirty = subprocess.run(
            [*git, "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if dirty.returncode == 0:
            identity["dirty"] = "true" if dirty.stdout.strip() else "false"
    except OSError:
        pass
    return identity


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def classify_exit(returncode: int, best_effort: bool) -> str:
    if returncode == 0:
        return "PASS"
    if returncode == 77:
        return "NOT_EXECUTED"
    # Optional tools may be absent (77), but a test that ran and failed must
    # remain a failure, including in all-safe. Never turn its error into a skip.
    return "FAIL"


def run_command(
    root: Path,
    argv: Sequence[str],
    log_path: Path,
    dry_run: bool,
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    started = time.monotonic()
    record: Dict[str, Any] = {
        "argv": list(argv),
        "dry_run": dry_run,
        "returncode": 0,
        "status": "PLANNED" if dry_run else "PASS",
        "log": str(log_path),
        "seconds": 0.0,
    }
    if dry_run:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("dry-run: " + " ".join(argv) + "\n", encoding="utf-8")
        return record
    merged = os.environ.copy()
    if env:
        merged.update(env)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(argv) + "\n")
        handle.flush()
        completed = subprocess.run(
            list(argv),
            cwd=root,
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=merged,
            check=False,
        )
    record["returncode"] = completed.returncode
    record["seconds"] = round(time.monotonic() - started, 3)
    return record


def engineering_steps() -> List[Dict[str, Any]]:
    return [
        {
            "id": "engineering-suite",
            "level": "engineering",
            "argv": ["bash", "scripts/tests/run_test_suite.sh", "engineering"],
            "required_tools": [],
            "best_effort": False,
        }
    ]


def operational_steps() -> List[Dict[str, Any]]:
    return [
        {
            "id": "operational-suite",
            "level": "operational",
            "argv": ["bash", "scripts/tests/run_test_suite.sh", "operational"],
            "required_tools": list(OPERATIONAL_TOOLS),
            "best_effort": False,
        }
    ]


def synthetic_steps() -> List[Dict[str, Any]]:
    return [
        {
            "id": "synthetic-benchmark",
            "level": "engineering",
            "argv": [
                sys.executable,
                "-m",
                "unittest",
                "scripts.tests.evidence.test_synthetic_benchmark",
            ],
            "required_tools": [],
            "best_effort": False,
        },
        {
            "id": "sample-classes",
            "level": "engineering",
            "argv": [
                sys.executable,
                "-m",
                "unittest",
                "scripts.tests.evidence.test_sample_classes",
            ],
            "required_tools": [],
            "best_effort": False,
        },
        {
            "id": "controls-contract",
            "level": "engineering",
            "argv": [
                sys.executable,
                "-m",
                "unittest",
                "scripts.tests.evidence.test_controls",
            ],
            "required_tools": [],
            "best_effort": False,
        },
    ]


def competitive_steps() -> List[Dict[str, Any]]:
    return [
        {
            "id": "competitive-margin",
            "level": "engineering",
            "argv": [
                sys.executable,
                "-m",
                "unittest",
                "scripts.tests.evidence.test_competitive_margin",
            ],
            "required_tools": [],
            "best_effort": False,
        },
        {
            "id": "blast-specificity-integrity",
            "level": "engineering",
            "argv": [
                sys.executable,
                "-m",
                "unittest",
                "scripts.tests.evidence.test_blast_specificity_integrity",
            ],
            "required_tools": [],
            "best_effort": False,
        },
        {
            "id": "blast-e2e-real",
            "level": "operational",
            "argv": ["bash", "scripts/tests/evidence/test_blast_e2e_real.sh"],
            "required_tools": ["blastn", "makeblastdb"],
            "best_effort": True,
        },
    ]


def expand_tracks(track: str) -> List[str]:
    if track == "all-safe":
        return ["engineering", "synthetic", "competitive", "operational"]
    return [track]


def steps_for_track(track: str) -> List[Dict[str, Any]]:
    mapping = {
        "engineering": engineering_steps,
        "operational": operational_steps,
        "synthetic": synthetic_steps,
        "competitive": competitive_steps,
    }
    return mapping[track]()


def execute_steps(
    root: Path,
    steps: Sequence[Mapping[str, Any]],
    log_dir: Path,
    dry_run: bool,
    best_effort_track: bool,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for step in steps:
        log_path = log_dir / f"{step['id']}.log"
        missing = which_missing(step.get("required_tools") or [])
        execute = bool(step.get("execute", True))
        best_effort = bool(step.get("best_effort")) or best_effort_track
        record: Dict[str, Any] = {
            "id": step["id"],
            "level": step["level"],
            "argv": list(step["argv"]),
            "best_effort": best_effort,
        }
        if not execute:
            record.update(
                {
                    "status": "PLANNED",
                    "returncode": 0,
                    "seconds": 0.0,
                    "log": str(log_path),
                    "note": "etapa planejada; habilite sua execução para continuar",
                }
            )
            if missing:
                record["missing_tools"] = missing
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "planned: " + " ".join(step["argv"]) + "\n",
                encoding="utf-8",
            )
            results.append(record)
            continue
        if missing:
            record.update(
                {
                    "status": "NOT_EXECUTED",
                    "returncode": 77,
                    "seconds": 0.0,
                    "log": str(log_path),
                    "missing_tools": missing,
                }
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "ferramentas ausentes: " + " ".join(missing) + "\n",
                encoding="utf-8",
            )
            results.append(record)
            continue
        ran = run_command(root, step["argv"], log_path, dry_run)
        status = "PLANNED" if dry_run else classify_exit(ran["returncode"], best_effort)
        record.update(
            {
                "status": status,
                "returncode": ran["returncode"],
                "seconds": ran["seconds"],
                "log": ran["log"],
            }
        )
        results.append(record)
    return results


def summarize(step_results: Sequence[Mapping[str, Any]]) -> str:
    statuses = [str(item["status"]) for item in step_results]
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if statuses and all(status == "BLOCKED" for status in statuses):
        return "BLOCKED"
    if statuses and all(status in {"NOT_EXECUTED", "BLOCKED"} for status in statuses):
        return "NOT_EXECUTED"
    if statuses and all(status in {"PASS", "PLANNED", "NOT_EXECUTED"} for status in statuses):
        if any(status == "PLANNED" for status in statuses) and not any(
            status == "PASS" for status in statuses
        ):
            return "PLANNED"
        return "PASS"
    if not statuses:
        return "BLOCKED"
    return "FAIL"


def exit_code_for(track: str, overall: str, expanded: Sequence[str]) -> int:
    if overall == "FAIL":
        return 1
    if overall in {"BLOCKED", "NOT_EXECUTED"}:
        if track == "all-safe":
            return 0
        return 77
    return 0


def _scientific_out_dir(root: Path, out: Optional[Path], stamp: str) -> Path:
    if out is None:
        return root / "results" / "validation" / stamp
    resolved = out if out.is_absolute() else root / out
    if resolved.suffix.lower() == ".json":
        return resolved.parent
    return resolved


def optimization_status(out_dir: Path, optimization_level: str) -> tuple[int, str]:
    if optimization_level in {"pipeline", "both"}:
        pipeline_dir = out_dir / "pipeline" if (out_dir / "pipeline" / "results.json").is_file() else out_dir
        results_path = pipeline_dir / "results.json"
        manifest_path = pipeline_dir / "manifest.json"
        if results_path.is_file():
            results = json.loads(results_path.read_text(encoding="utf-8"))
            statuses = {str(row.get("status")) for row in results}
            missing = []
            if manifest_path.is_file():
                missing = json.loads(manifest_path.read_text(encoding="utf-8")).get("missing_tools") or []
            if missing or (statuses and statuses <= {"NOT_EXECUTED"}):
                return 77, "NOT_EXECUTED"
            if "FAIL" in statuses:
                return 1, "FAIL"
            return 0, "PASS"
    return 0, "PASS"


def run_scientific_optimization(root: Path, args: argparse.Namespace, out_dir: Path, dry_run: bool) -> Dict[str, Any]:
    from validation.optimization import run_optimization
    if dry_run:
        return {
            "id": "scientific-optimization",
            "level": "scientific-optimization",
            "argv": ["scientific-optimization", f"--optimization-level={args.optimization_level}"],
            "status": "PLANNED",
            "returncode": 0,
            "seconds": 0.0,
            "note": "dry-run; contract/pipeline not executed",
        }
    started = time.monotonic()
    experiment_id = args.experiment_id or f"validation-{git_identity(root)['commit'][:8]}"
    manifest = run_optimization(
        repo_root=root,
        grid_path=Path(args.grid),
        panel_path=Path(args.panel),
        pipeline_panel_path=Path(args.pipeline_panel),
        out_dir=out_dir,
        experiment_id=experiment_id,
        optimization_level=args.optimization_level,
        top_n=args.top_n,
        pinned_parameter_sets=Path(args.pinned_parameter_sets) if args.pinned_parameter_sets else None,
    )
    code, status = optimization_status(out_dir, args.optimization_level)
    return {
        "id": "scientific-optimization",
        "level": "scientific-optimization",
        "argv": ["scientific-optimization", f"--optimization-level={args.optimization_level}"],
        "status": status,
        "returncode": code,
        "seconds": round(time.monotonic() - started, 3),
        "manifest": manifest,
        "optimization_level": args.optimization_level,
        "not_pipeline_recovery": args.optimization_level == "contract",
    }


def run_contract_selftest_track(root: Path, args: argparse.Namespace, out_dir: Path, dry_run: bool) -> Dict[str, Any]:
    from validation.contract_selftest import run_contract_selftest
    if dry_run:
        return {
            "id": "contract-selftest",
            "level": "contract-selftest",
            "argv": ["contract-selftest"],
            "status": "PLANNED",
            "returncode": 0,
            "seconds": 0.0,
            "note": "dry-run; frozen parameter set not evaluated",
        }
    started = time.monotonic()
    experiment_id = args.experiment_id or f"validation-selftest-{git_identity(root)['commit'][:8]}"
    report = run_contract_selftest(
        repo_root=root,
        parameter_set_path=Path(args.parameter_set),
        validation_panel_path=Path(args.validation_panel),
        development_panel_path=Path(args.development_panel) if args.development_panel else None,
        criteria_path=Path(args.criteria),
        out_dir=out_dir,
        experiment_id=experiment_id,
    )
    return {
        "id": "contract-selftest",
        "level": "contract-selftest",
        "argv": ["contract-selftest"],
        "status": "PASS",
        "returncode": 0,
        "seconds": round(time.monotonic() - started, 3),
        "contract_selftest_report": report,
        "note": "Contract self-test completed on synthetic samples; not an independent validation.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Orquestra análises e testes do Validation."
        )
    )
    parser.add_argument(
        "--track",
        default="",
        help="engineering|operational|synthetic|competitive|all-safe|scientific-optimization|contract-selftest",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Arquivo JSON de saida ou diretorio. Padrao: results/validation/<stamp>/report.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista comandos e escreve o relatorio sem executar testes pesados",
    )
    parser.add_argument(
        "--list-tracks",
        action="store_true",
        help="Lista faixas conhecidas e sai",
    )
    parser.add_argument("--experiment-id", default="")
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--panel", type=Path, default=DEFAULT_DEV_PANEL)
    parser.add_argument("--pipeline-panel", type=Path, default=DEFAULT_PIPELINE_PANEL)
    parser.add_argument("--validation-panel", type=Path, default=DEFAULT_VAL_PANEL)
    parser.add_argument("--development-panel", type=Path, default=DEFAULT_DEV_PANEL)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--parameter-set", type=Path, help="Frozen parameter set JSON for contract-selftest")
    parser.add_argument(
        "--optimization-level",
        choices=["contract", "pipeline", "both"],
        default="contract",
        help="contract=fixtures; pipeline=etapas reais do Gene-In; both=contrato depois pipeline",
    )
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument(
        "--pinned-parameter-sets",
        type=Path,
        default=None,
        help=(
            "Optional JSON listing experimental parameter-set overrides to run "
            "in optimization-pipeline instead of ranking selection. Used to "
            "repeat round-1 sets. Does not change canonical thresholds."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_tracks:
        print("\n".join(VALID_TRACKS))
        return 0
    track = str(args.track).strip().lower()
    if not track:
        print("[USAGE] --track e obrigatorio.", file=sys.stderr)
        return 2
    if track not in VALID_TRACKS:
        print(
            f"[USAGE] faixa invalida {track!r}. Use: {', '.join(VALID_TRACKS)}",
            file=sys.stderr,
        )
        return 2
    if track == "contract-selftest" and not args.parameter_set:
        print("[USAGE] contract-selftest exige --parameter-set.", file=sys.stderr)
        return 2

    try:
        bundle_path = ensure_genein_bundle_path()
    except FileNotFoundError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 2
    if bundle_path:
        print(f"[VALIDATION] usando env isolado: {bundle_path}")

    root = repo_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out
    if out is None:
        report_path = root / "results" / "validation" / stamp / "report.json"
    elif out.suffix.lower() == ".json":
        report_path = out if out.is_absolute() else root / out
    else:
        report_path = (out if out.is_absolute() else root / out) / "report.json"
    log_dir = report_path.parent / "logs"

    expanded = expand_tracks(track)
    step_results: List[Dict[str, Any]] = []
    scientific_meta: Optional[Dict[str, Any]] = None
    for item in expanded:
        best_effort_track = track == "all-safe" and item == "operational"
        if item == "scientific-optimization":
            sci_dir = _scientific_out_dir(root, args.out, stamp)
            record = run_scientific_optimization(root, args, sci_dir, args.dry_run)
            step_results.append(record)
            scientific_meta = {
                "optimization_level": args.optimization_level,
                "not_pipeline_recovery": args.optimization_level == "contract",
            }
            continue
        if item == "contract-selftest":
            sci_dir = _scientific_out_dir(root, args.out, stamp)
            record = run_contract_selftest_track(root, args, sci_dir, args.dry_run)
            step_results.append(record)
            scientific_meta = {"frozen_parameter_set": str(args.parameter_set), "tunes_parameters": False}
            continue
        steps = steps_for_track(item)
        if best_effort_track:
            steps = [{**step, "best_effort": True} for step in steps]
        step_results.extend(
            execute_steps(root, steps, log_dir, args.dry_run, best_effort_track)
        )

    overall = summarize(step_results)
    report = {
        "schema": SCHEMA,
        "track": track,
        "expanded_tracks": list(expanded),
        "status": overall,
        "dry_run": bool(args.dry_run),
        "created_at": utc_now(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git": git_identity(root),
        "steps": step_results,
        "scientific": scientific_meta,
    }
    atomic_write_json(report_path, report)
    print(f"[VALIDATION] track={track} status={overall}")
    for step in step_results:
        print(f"[VALIDATION] {step['id']}: {step['status']}")
    print(f"[VALIDATION] report={report_path}")
    return exit_code_for(track, overall, expanded)


if __name__ == "__main__":
    sys.exit(main())
