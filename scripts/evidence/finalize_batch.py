#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

try:
    from .activation_policy import validate_policy_identity
    from .common import (
        build_artifact_manifest, fsync_directory, read_tsv, sha256_file,
        validate_artifact_manifest, write_json_atomic,
    )
    from .evidence_contract import (
        PIPELINE_VERSION, promote_for_public_output, validate_document,
    )
    from .run_state import read_state
    from .run_state import state_lock
    from .validate_run_artifacts import validate
except ImportError:
    from activation_policy import validate_policy_identity
    from common import (
        build_artifact_manifest, fsync_directory, read_tsv, sha256_file,
        validate_artifact_manifest, write_json_atomic,
    )
    from evidence_contract import (
        PIPELINE_VERSION, promote_for_public_output, validate_document,
    )
    from run_state import read_state
    from run_state import state_lock
    from validate_run_artifacts import validate


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def promote_directory(staging: Path, final: Path) -> None:
    os.replace(staging, final)


def validate_batch_evidence(
    path: Path, expected_run_id: str, expected_identity: dict,
) -> dict:
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        value = promote_for_public_output(
            json.load(handle), expected_identity=expected_identity,
        )
    if value["run_id"] != expected_run_id:
        raise ValueError("batch evidence run_id does not match the batch state")
    return value


def validate_batch_identity(state: dict, batch: dict, rows: list[dict[str, str]],
                            staging: Path, final: Path) -> None:
    run_id = state.get("run_id")
    if state.get("action") != "evidence_batch":
        raise ValueError("batch finalizer requires evidence_batch state")
    if batch.get("run_id") != run_id or batch.get("batch_id") != state.get("batch_id"):
        raise ValueError("batch evidence identity does not match run state")
    state_identity = validate_policy_identity(state, context="batch run state")
    validate_policy_identity(batch, expected=state_identity, context="batch evidence")
    row_samples = [row.get("sample_id", "") for row in rows]
    if len(row_samples) != len(set(row_samples)) or row_samples != state.get("sample_ids"):
        raise ValueError("run map samples do not match run state")
    if staging.name != run_id or final.name != run_id:
        raise ValueError("staging and final directories must match run_id")
    if state.get("status") in {"done", "done_with_warning", "blocked", "failed", "cancelled"}:
        raise ValueError(f"batch state is already terminal: {state.get('status')}")


def validate_source_sample(
    sample_dir: Path, row: dict[str, str], expected_identity: dict,
) -> None:
    source_success_path = sample_dir / "SUCCESS.json"
    if not source_success_path.is_file():
        source_success_path = sample_dir / "SOURCE_SUCCESS.json"
    if not source_success_path.is_file():
        raise ValueError(f"resultado incompleto da amostra {row['sample_id']}")
    source_success = json.loads(source_success_path.read_text(encoding="utf-8", errors="strict"))
    if source_success.get("status") not in {"done", "done_with_warning"}:
        raise ValueError(f"execução filha não concluída da amostra {row['sample_id']}")
    if source_success.get("run_id") != row.get("run_id"):
        raise ValueError(f"run_id da execução filha não corresponde à amostra {row['sample_id']}")
    with (sample_dir / "sample_evidence.json").open("r", encoding="utf-8", errors="strict") as handle:
        evidence = validate_document(json.load(handle))
    if evidence.get("sample_id") != row.get("sample_id") or evidence.get("run_id") != row.get("run_id"):
        raise ValueError(f"identidade científica divergente da amostra {row['sample_id']}")
    validate_policy_identity(
        source_success, expected=expected_identity,
        context=f"SUCCESS da amostra {row['sample_id']}",
    )
    validate_policy_identity(
        evidence, expected=expected_identity,
        context=f"evidência da amostra {row['sample_id']}",
    )


def write_sample_commit(sample_dir: Path, row: dict[str, str], parent_run_id: str,
                        parent_state: dict) -> None:
    source_success_path = sample_dir / "SUCCESS.json"
    if not source_success_path.is_file():
        source_success_path = sample_dir / "SOURCE_SUCCESS.json"
    if not source_success_path.is_file():
        raise ValueError(f"resultado incompleto da amostra {row['sample_id']}")
    source_success = json.loads(source_success_path.read_text(encoding="utf-8", errors="strict"))
    if source_success.get("status") not in {"done", "done_with_warning"}:
        raise ValueError(f"execução filha não concluída da amostra {row['sample_id']}")
    source_copy = sample_dir / "SOURCE_SUCCESS.json"
    if not source_copy.exists():
        write_json_atomic(source_copy, source_success)
    (sample_dir / "SUCCESS.json").unlink(missing_ok=True)
    old_manifest = sample_dir / "artifact_manifest.json"
    if old_manifest.exists():
        old_manifest.unlink()
    errors = validate(sample_dir)
    if errors:
        raise ValueError(f"amostra {row['sample_id']}: {'; '.join(errors)}")
    with (sample_dir / "sample_evidence.json").open("r", encoding="utf-8", errors="strict") as handle:
        validate_document(json.load(handle))
    manifest = build_artifact_manifest(sample_dir)
    write_json_atomic(sample_dir / "artifact_manifest.json", manifest)
    manifest_errors = validate_artifact_manifest(sample_dir, manifest)
    if manifest_errors:
        raise ValueError(f"amostra {row['sample_id']}: {'; '.join(manifest_errors)}")
    write_json_atomic(sample_dir / "SUCCESS.json", {
        "run_id": row["run_id"], "parent_run_id": parent_run_id,
        "pipeline_version": PIPELINE_VERSION,
        **validate_policy_identity(parent_state, context="batch run state"),
        "status": source_success.get("status", "done"), "completed_at": now(),
        "shadow_mode": parent_state.get("shadow_mode", False), "artifact_count": len(manifest["files"]),
        "artifact_manifest_sha256": sha256_file(sample_dir / "artifact_manifest.json"),
        "sample_evidence_sha256": sha256_file(sample_dir / "sample_evidence.json"),
    })
    fsync_directory(sample_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and atomically promote an Evidence V2 batch")
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--run-map", required=True, type=Path)
    args = parser.parse_args()
    if args.final.exists():
        raise FileExistsError(f"diretório final já existe: {args.final}")
    args.final.parent.mkdir(parents=True, exist_ok=True)
    if args.staging.stat().st_dev != args.final.parent.stat().st_dev:
        raise ValueError("batch staging and final directory must share a filesystem")
    if (args.staging / "SUCCESS.json").exists():
        raise ValueError("batch staging contains an invalid pre-existing SUCCESS.json")
    if (args.staging / "artifact_manifest.json").is_file():
        (args.staging / "artifact_manifest.json").unlink()
    rows = read_tsv(args.run_map)
    required = [
        "batch_manifest.tsv", "batch_evidence.json", "control_status.tsv",
        "batch_report.md", "provenance.json",
    ]
    missing = [name for name in required if not (args.staging / name).is_file()]
    if missing:
        raise ValueError("artefatos de lote ausentes: " + ", ".join(missing))
    with state_lock(args.state):
        state = read_state(args.state)
        state_identity = validate_policy_identity(state, context="batch run state")
        batch = validate_batch_evidence(
            args.staging / "batch_evidence.json", state["run_id"], state_identity,
        )
        validate_batch_identity(state, batch, rows, args.staging, args.final)
        # Validate every child identity before mutating any child commit.
        for row in rows:
            validate_source_sample(
                args.staging / "samples" / row["sample_id"], row, state_identity,
            )
        for row in rows:
            write_sample_commit(args.staging / "samples" / row["sample_id"], row, state["run_id"], state)

        work = (args.staging / "work").resolve()
        work.relative_to(args.staging.resolve())
        if work.exists():
            shutil.rmtree(work)
        state["status"] = "done_with_warning" if state.get("warnings") else "done"
        state["evidence_v2_status"] = state["status"]
        state["execution_status"] = "warning" if state["status"] == "done_with_warning" else "done"
        state["current_stage"] = None
        state["finished_at"] = now()
        state["artifacts"].update({
            "batch_evidence": f"runs/{state['run_id']}/batch_evidence.json",
            "control_status": f"runs/{state['run_id']}/control_status.tsv",
            "report": f"runs/{state['run_id']}/batch_report.md",
        })
        write_json_atomic(args.staging / "run_state.json", state)
        errors = validate(args.staging)
        if errors:
            raise ValueError("; ".join(errors))
        manifest = build_artifact_manifest(args.staging)
        write_json_atomic(args.staging / "artifact_manifest.json", manifest)
        manifest_errors = validate_artifact_manifest(args.staging, manifest)
        if manifest_errors:
            (args.staging / "artifact_manifest.json").unlink(missing_ok=True)
            raise ValueError("; ".join(manifest_errors))
        success = {
            "run_id": state["run_id"], "pipeline_version": PIPELINE_VERSION,
            **validate_policy_identity(state, context="batch run state"),
            "status": state["status"], "completed_at": now(),
            "batch_evidence_sha256": sha256_file(args.staging / "batch_evidence.json"),
            "artifact_manifest_sha256": sha256_file(args.staging / "artifact_manifest.json"),
        "artifact_count": len(manifest["files"]), "sample_count": len(rows),
        "shadow_mode": state.get("shadow_mode", False),
        }
        fsync_directory(args.staging)
        try:
            promote_directory(args.staging, args.final)
        except Exception:
            (args.staging / "artifact_manifest.json").unlink(missing_ok=True)
            fsync_directory(args.staging)
            raise
        fsync_directory(args.final.parent)
        try:
            # The promoted batch remains invalid until this final commit write.
            write_json_atomic(args.final / "SUCCESS.json", success)
            fsync_directory(args.final)
            write_json_atomic(args.state, state)
        except Exception:
            (args.final / "SUCCESS.json").unlink(missing_ok=True)
            fsync_directory(args.final)
            try:
                os.replace(args.final, args.staging)
                (args.staging / "artifact_manifest.json").unlink(missing_ok=True)
                fsync_directory(args.final.parent)
            except Exception:
                pass
            raise
    print(args.final)


if __name__ == "__main__":
    main()
