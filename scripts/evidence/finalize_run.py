#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from .activation_policy import (
        POLICY_IDENTITY_FIELDS,
        load_experimental_activation_policy,
        load_public_activation_policy,
        validate_policy_identity,
    )
    from .common import (
        build_artifact_manifest, fsync_directory, sha256_file,
        validate_artifact_manifest, write_json_atomic,
    )
    from .run_state import read_state, state_lock
    from .validate_run_artifacts import validate
except ImportError:
    from activation_policy import (
        POLICY_IDENTITY_FIELDS,
        load_experimental_activation_policy,
        load_public_activation_policy,
        validate_policy_identity,
    )
    from common import (
        build_artifact_manifest, fsync_directory, sha256_file,
        validate_artifact_manifest, write_json_atomic,
    )
    from run_state import read_state, state_lock
    from validate_run_artifacts import validate


def _load_policy(args: argparse.Namespace) -> dict | None:
    """Same public/experimental resolution used by scripts/evidence/run.sh.

    ``None`` preserves the historical default of validating against the
    active public policy when neither flag is given.
    """
    if getattr(args, "experimental_activation_policy", None):
        return load_experimental_activation_policy(
            args.experimental_activation_policy, profiles_path=args.profiles,
        )
    if getattr(args, "activation_policy", None):
        return load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)
    return None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def remove_commit_metadata(directory: Path) -> None:
    (directory / "SUCCESS.json").unlink(missing_ok=True)
    (directory / "artifact_manifest.json").unlink(missing_ok=True)
    fsync_directory(directory)


def promote_directory(staging: Path, final: Path) -> None:
    os.replace(staging, final)


def validate_identity(
    state: dict,
    evidence: dict,
    staging: Path,
    final: Path,
    *,
    historical_compatibility: str | None = None,
) -> None:
    run_id = state.get("run_id")
    if state.get("action") != "evidence_single":
        raise ValueError("single-run finalizer requires evidence_single state")
    if evidence.get("run_id") != run_id:
        raise ValueError("sample evidence run_id does not match run state")
    if state.get("sample_ids") != [evidence.get("sample_id")]:
        raise ValueError("sample evidence sample_id does not match run state")
    if historical_compatibility is not None:
        if historical_compatibility != "historical_alpha2_fixture":
            raise ValueError("unsupported historical finalization context")
        if (
            state.get("policy_version") != "2.0-alpha"
            or state.get("shadow_mode") is not True
            or evidence.get("run_id") != "fixture-alpha2-run"
            or evidence.get("sample_id") != "fixture-alpha2"
            or evidence.get("provenance") != {"fixture": True}
            or any(field in state for field in POLICY_IDENTITY_FIELDS if field != "shadow_mode")
            or any(field in evidence for field in POLICY_IDENTITY_FIELDS if field != "shadow_mode")
        ):
            raise ValueError("historical Alpha.2 finalization is restricted to the frozen fixture")
    else:
        state_identity = validate_policy_identity(state, context="run state")
        validate_policy_identity(
            evidence, expected=state_identity, context="sample evidence",
        )
    if staging.name != run_id or final.name != run_id:
        raise ValueError("staging and final directories must match run_id")
    if state.get("status") in {"done", "done_with_warning", "blocked", "failed", "cancelled"}:
        raise ValueError(f"run state is already terminal: {state.get('status')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and atomically promote an Evidence V2 run")
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--historical-alpha2-fixture", action="store_true")
    policy_group = parser.add_mutually_exclusive_group()
    policy_group.add_argument("--activation-policy")
    policy_group.add_argument("--experimental-activation-policy")
    parser.add_argument("--profiles")
    args = parser.parse_args()
    policy = _load_policy(args)
    if args.final.exists():
        raise FileExistsError(f"final run directory already exists: {args.final}")
    args.final.parent.mkdir(parents=True, exist_ok=True)
    if args.staging.stat().st_dev != args.final.parent.stat().st_dev:
        raise ValueError("run staging and final directory must share a filesystem")
    if (args.staging / "SUCCESS.json").exists():
        raise ValueError("staging contains an invalid pre-existing SUCCESS.json")
    if (args.staging / "artifact_manifest.json").is_file() and not (args.staging / "SUCCESS.json").exists():
        # Recover a staging directory left after a failed promotion attempt.
        (args.staging / "artifact_manifest.json").unlink()
    historical_compatibility = (
        "historical_alpha2_fixture" if args.historical_alpha2_fixture else None
    )
    errors = validate(args.staging, policy=policy, compatibility_mode=historical_compatibility)
    if errors:
        raise ValueError("; ".join(errors))
    with (args.staging / "sample_evidence.json").open("r", encoding="utf-8", errors="strict") as handle:
        evidence = json.load(handle)
    with state_lock(args.state):
        state = read_state(args.state)
        validate_identity(
            state, evidence, args.staging, args.final,
            historical_compatibility=historical_compatibility,
        )
        status = "done_with_warning" if state.get("warnings") else "done"
        final_state = dict(state)
        final_state.update({
            "status": status,
            "evidence_v2_status": status,
            "execution_status": evidence["execution_status"],
            "analysis_outcome": evidence["analysis_outcome"],
            "evidence_level": evidence["evidence_level"],
            "current_stage": None,
            "finished_at": now(),
        })
        write_json_atomic(args.staging / "run_state.json", final_state)
        manifest = build_artifact_manifest(args.staging)
        write_json_atomic(args.staging / "artifact_manifest.json", manifest)
        manifest_errors = validate_artifact_manifest(args.staging, manifest)
        if manifest_errors:
            remove_commit_metadata(args.staging)
            raise ValueError("; ".join(manifest_errors))
        success = {
            "run_id": state["run_id"], "pipeline_version": state["pipeline_version"],
            "shadow_mode": state["shadow_mode"],
            "status": status, "validated_at": final_state["finished_at"],
            "artifact_count": len(manifest["files"]),
            "artifact_manifest_sha256": sha256_file(args.staging / "artifact_manifest.json"),
            "sample_evidence_sha256": sha256_file(args.staging / "sample_evidence.json"),
        }
        if historical_compatibility is None:
            success.update(validate_policy_identity(state, context="run state"))
            success["mapper_source_version"] = "0.2.2"
        else:
            success["policy_version"] = state.get("policy_version")
        fsync_directory(args.staging)
        try:
            promote_directory(args.staging, args.final)
        except Exception:
            remove_commit_metadata(args.staging)
            raise
        fsync_directory(args.final.parent)
        try:
            # The promoted directory remains invalid until this final commit write.
            write_json_atomic(args.final / "SUCCESS.json", success)
            fsync_directory(args.final)
            write_json_atomic(args.state, final_state)
        except Exception:
            # Never leave a valid committed run paired with stale external state.
            (args.final / "SUCCESS.json").unlink(missing_ok=True)
            fsync_directory(args.final)
            try:
                os.replace(args.final, args.staging)
                remove_commit_metadata(args.staging)
                fsync_directory(args.final.parent)
            except Exception:
                # The final directory remains invalid because SUCCESS was removed.
                pass
            raise
    print(args.final)


if __name__ == "__main__":
    main()
