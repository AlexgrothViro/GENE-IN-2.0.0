#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import write_json_atomic
    from .activation_policy import (
        load_experimental_activation_policy,
        load_public_activation_policy,
        policy_identity,
        validate_policy_identity,
    )
    from .evidence_contract import not_evaluable_document
except ImportError:
    from common import write_json_atomic
    from activation_policy import (
        load_experimental_activation_policy,
        load_public_activation_policy,
        policy_identity,
        validate_policy_identity,
    )
    from evidence_contract import not_evaluable_document


PIPELINE_VERSION = "2.0.0-alpha.2"
RUN_STATUSES = {"queued", "running", "done", "done_with_warning", "blocked", "failed", "cancelled"}
STAGE_STATUSES = {"pending", "running", "done", "warning", "blocked", "failed", "cancelled"}
FAILURE_TYPES = {
    "DEPENDENCY_MISSING", "CONFIG_INVALID", "INPUT_INVALID", "TOOL_FAILURE",
    "ARTIFACT_INVALID", "CANCELLED", "CANCELLATION_FAILED", "UNKNOWN",
    "MEMORY_EXHAUSTED", "PROCESS_KILLED", "PROCESS_TERMINATED",
}
STAGES = [
    ("input_validation", "Validação da entrada"),
    ("quality_control", "Controle de qualidade"),
    ("assembly", "Montagem"),
    ("initial_blast", "BLAST inicial"),
    ("hsp_aggregation", "Agregação de HSPs"),
    ("locus_building", "Construção de loci"),
    ("competitive_search", "Busca competitiva"),
    ("read_remapping", "Remapeamento das reads"),
    ("coverage", "Cálculo de cobertura"),
    ("controls", "Avaliação de controles"),
    ("evidence_classification", "Geração de evidências"),
    ("report_export", "Exportação do relatório"),
]
V1_HANDOFF_STAGES = {"input_validation", "quality_control", "assembly", "initial_blast"}
TERMINAL_RUN_STATUSES = {"done", "done_with_warning", "blocked", "failed", "cancelled"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def state_lock(path: Path, *, timeout_seconds: float = 30.0,
               stale_after_seconds: float = 3600.0):
    """Serialize state read-modify-write cycles across Windows and WSL.

    A lock directory is used because its creation is atomic on the shared
    filesystem. Abandoned locks can be reclaimed only after a conservative
    stale interval.
    """
    path = path.resolve()
    lock_root = path.parent / ".locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_dir = lock_root / f"{path.name}.lock"
    token = uuid.uuid4().hex
    started = time.monotonic()
    while True:
        try:
            lock_dir.mkdir()
        except FileExistsError:
            try:
                age = time.time() - lock_dir.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > stale_after_seconds:
                stale = lock_root / f".{path.name}.stale.{uuid.uuid4().hex}"
                try:
                    os.replace(lock_dir, stale)
                except (FileNotFoundError, FileExistsError, PermissionError, OSError):
                    pass
                else:
                    shutil.rmtree(stale)
                    continue
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError(f"timed out waiting for run state lock: {path}")
            time.sleep(0.02)
            continue
        break

    owner = lock_dir / "owner.json"
    try:
        owner.write_text(
            json.dumps({"token": token, "pid": os.getpid(), "created_at": now()}) + "\n",
            encoding="utf-8",
        )
    except Exception:
        try:
            lock_dir.rmdir()
        except OSError:
            pass
        raise
    try:
        yield
    finally:
        current = {}
        for attempt in range(40):
            try:
                current = json.loads(owner.read_text(encoding="utf-8"))
                break
            except PermissionError:
                if os.name != "nt" or attempt == 39:
                    break
                time.sleep(min(0.005 * (attempt + 1), 0.1))
            except (FileNotFoundError, ValueError, json.JSONDecodeError):
                break
        if current.get("token") == token:
            for attempt in range(40):
                try:
                    owner.unlink(missing_ok=True)
                    lock_dir.rmdir()
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    if os.name != "nt" or attempt == 39:
                        raise
                    time.sleep(min(0.005 * (attempt + 1), 0.1))


def mutate_state_file(path: Path, mutator) -> dict:
    with state_lock(path):
        state = read_state(path)
        mutator(state)
        write_json_atomic(path, state)
        return state


def _validate_run_transition(current: str, requested: str) -> None:
    if current not in RUN_STATUSES:
        raise ValueError(f"invalid current run status: {current}")
    if requested == current:
        return
    if current in TERMINAL_RUN_STATUSES:
        raise ValueError(
            f"run already terminal ({current}); refusing transition to {requested}"
        )
    allowed = {
        "queued": {"running", "blocked", "failed", "cancelled"},
        "running": {"done", "done_with_warning", "blocked", "failed", "cancelled"},
    }
    if requested not in allowed[current]:
        raise ValueError(f"invalid run transition: {current} -> {requested}")


def initial_state(
    run_id: str,
    action: str,
    samples: list[str],
    batch_id: str | None,
    policy: dict | None = None,
) -> dict:
    active_policy = policy or load_public_activation_policy()
    identity = policy_identity(active_policy)
    return {
        "run_id": run_id,
        "pipeline_version": PIPELINE_VERSION,
        **identity,
        "scientific_role": active_policy["scientific_role"],
        "shadow_mode": active_policy["shadow_mode"],
        "evidence_ceiling": active_policy["evidence_ceiling"],
        "execution_status": "queued",
        "analysis_outcome": None,
        "evidence_level": None,
        "action": action,
        "sample_ids": samples,
        "batch_id": batch_id or None,
        "status": "queued",
        "official_v1_status": "not_started",
        "evidence_v2_status": "queued",
        "current_stage": None,
        "created_at": now(),
        "started_at": None,
        "finished_at": None,
        "stages": [
            {"id": stage_id, "label": label, "status": "pending", "started_at": None,
             "finished_at": None, "message": None}
            for stage_id, label in STAGES
        ],
        "warnings": [],
        "failed_stage": None,
        "failure_type": None,
        "failure_message": None,
        "failed_command": None,
        "artifacts": {},
        "provenance": {},
    }


def _exclusive_marker(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        data = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _owner_marker(path: Path) -> Path:
    return path.parent / ".owners" / f"{path.name}.owner"


def _claim_marker(path: Path) -> Path:
    return path.parent / ".claims" / f"{path.name}.claim"


def _create_state_exclusive(path: Path, state: dict, owner: str) -> None:
    """Create a run state exactly once without ever replacing an older state."""
    if path.exists():
        raise FileExistsError(f"run state already exists: {path}")
    marker = _owner_marker(path)
    _exclusive_marker(marker, {"run_id": state["run_id"], "owner": owner, "created_at": now()})
    try:
        if path.exists():
            raise FileExistsError(f"run state already exists: {path}")
        write_json_atomic(path, state)
    except Exception:
        marker.unlink(missing_ok=True)
        raise


def reservation_digest(token: str) -> str:
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("reservation token must contain at least 32 characters")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def reserve_state(path: Path, run_id: str, action: str, samples: list[str],
                  batch_id: str | None, reservation_token: str,
                  policy: dict | None = None) -> dict:
    state = initial_state(run_id, action, samples, batch_id, policy)
    state["reservation"] = {
        "status": "reserved",
        "owner": "dashboard",
        "token_sha256": reservation_digest(reservation_token),
        "reserved_at": now(),
        "claimed_at": None,
    }
    _create_state_exclusive(path, state, "dashboard")
    return state


def initialize_runner_state(path: Path, run_id: str, action: str, samples: list[str],
                            batch_id: str | None, policy: dict | None = None) -> dict:
    state = initial_state(run_id, action, samples, batch_id, policy)
    state["reservation"] = {
        "status": "claimed",
        "owner": "evidence_runner",
        "token_sha256": None,
        "reserved_at": None,
        "claimed_at": now(),
    }
    _create_state_exclusive(path, state, "evidence_runner")
    return state


def _validate_adoptable_state(state: dict, *, run_id: str, action: str,
                              samples: list[str], batch_id: str | None,
                              reservation_token: str, staging: Path,
                              final: Path, identity: dict) -> None:
    if state.get("run_id") != run_id or state.get("action") != action:
        raise ValueError("reserved state does not match the requested run")
    if state.get("sample_ids") != samples or (state.get("batch_id") or None) != (batch_id or None):
        raise ValueError("reserved state does not match the requested samples or batch")
    validate_policy_identity(state, expected=identity, context="reserved run state")
    reservation = state.get("reservation")
    if not isinstance(reservation, dict) or reservation.get("status") != "reserved":
        raise FileExistsError("run state is not an unclaimed dashboard reservation")
    if reservation.get("token_sha256") != reservation_digest(reservation_token):
        raise PermissionError("reservation token does not match this run")
    if state.get("status") not in {"queued", "running"}:
        raise FileExistsError("reserved state is already terminal")
    if state.get("evidence_v2_status") not in {"queued", "running"}:
        raise FileExistsError("Evidence V2 state is not adoptable")
    if state.get("finished_at") or state.get("artifacts") or state.get("provenance"):
        raise FileExistsError("reserved state contains artifacts or completion metadata")
    for stage in state.get("stages", []):
        if stage.get("id") not in V1_HANDOFF_STAGES and stage.get("status") != "pending":
            raise FileExistsError("reserved state has already entered an Evidence V2-only stage")
        if stage.get("status") in {"blocked", "failed", "cancelled"}:
            raise FileExistsError("reserved state contains a terminal stage")
    if staging.exists() or final.exists() or (final / "SUCCESS.json").exists():
        raise FileExistsError("staging or final run already exists")


def adopt_reserved_state(path: Path, *, run_id: str, action: str,
                         samples: list[str], batch_id: str | None,
                         reservation_token: str, staging: Path,
                         final: Path, policy: dict | None = None) -> dict:
    """Atomically claim a dashboard reservation for exactly one runner."""
    claim = _claim_marker(path)
    _exclusive_marker(claim, {"run_id": run_id, "owner": "evidence_runner", "claimed_at": now()})
    identity = policy_identity(policy or load_public_activation_policy())
    try:
        with state_lock(path):
            state = read_state(path)
            _validate_adoptable_state(
                state, run_id=run_id, action=action, samples=samples, batch_id=batch_id,
                reservation_token=reservation_token, staging=staging, final=final,
                identity=identity,
            )
            state["reservation"].update({
                "status": "claimed", "owner": "evidence_runner", "claimed_at": now(),
            })
            write_json_atomic(path, state)
            return state
    except Exception:
        claim.unlink(missing_ok=True)
        raise


def read_state(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("run_id") is None or not isinstance(state.get("stages"), list):
        raise ValueError(f"invalid run state: {path}")
    return state


def set_stage(state: dict, stage_id: str, status: str, message: str | None) -> None:
    if status not in STAGE_STATUSES:
        raise ValueError(f"invalid stage status: {status}")
    stage = next((item for item in state["stages"] if item["id"] == stage_id), None)
    if stage is None:
        raise ValueError(f"unknown stage: {stage_id}")
    terminal = {"done", "warning", "blocked", "failed", "cancelled"}
    if stage["status"] in terminal:
        if status == stage["status"]:
            if message is not None:
                stage["message"] = message
            return
        if status == "running":
            # A pipeline handoff may replay already completed V1.1 stages.
            # Treat that request as an idempotent no-op; never regress state.
            return
        raise ValueError(
            f"stage {stage_id} already terminal ({stage['status']}); refusing transition to {status}"
        )
    if status == "running" and not stage["started_at"]:
        stage["started_at"] = now()
    if status == "running":
        stage["finished_at"] = None
    if status in {"done", "warning", "blocked", "failed", "cancelled"}:
        stage["started_at"] = stage["started_at"] or now()
        stage["finished_at"] = now()
    stage["status"] = status
    if message is not None:
        stage["message"] = message
    state["current_stage"] = stage_id if status == "running" else None
    if status == "warning" and message and message not in state["warnings"]:
        state["warnings"].append(message)


def set_failure(state: dict, failure_type: str, stage_id: str | None,
                message: str | None, command: str | None) -> None:
    if failure_type not in FAILURE_TYPES:
        raise ValueError(f"invalid failure type: {failure_type}")
    state["failure_type"] = failure_type
    state["failed_stage"] = stage_id or state.get("current_stage")
    state["failure_message"] = message
    state["failed_command"] = command


def write_failure_evidence(state: dict, root: Path, reason: str, policy: dict) -> None:
    identity = validate_policy_identity(
        state, expected=policy_identity(policy), context="run state",
    )
    for sample_id in state["sample_ids"]:
        output = root / "sample_evidence.json" if len(state["sample_ids"]) == 1 else (
            root / "samples" / sample_id / "sample_evidence.json"
        )
        write_json_atomic(
            output,
            not_evaluable_document(
                sample_id, state["run_id"], reason, state.get("provenance"),
                policy=policy,
            ),
        )


def _add_policy_arguments(command: argparse.ArgumentParser) -> None:
    group = command.add_mutually_exclusive_group()
    group.add_argument("--activation-policy", type=Path)
    group.add_argument("--experimental-activation-policy", type=Path)
    command.add_argument("--profiles", type=Path)


def _policy_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    if args.experimental_activation_policy:
        return load_experimental_activation_policy(
            args.experimental_activation_policy,
            profiles_path=args.profiles,
        )
    return load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atomically maintain Evidence V2 structured run state")
    parser.add_argument("--state", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--run-id", required=True)
    init.add_argument("--action", choices=["evidence_single", "evidence_batch"], required=True)
    init.add_argument("--sample", action="append", required=True)
    init.add_argument("--batch-id")
    _add_policy_arguments(init)
    reserve = sub.add_parser("reserve")
    reserve.add_argument("--run-id", required=True)
    reserve.add_argument("--action", choices=["evidence_single", "evidence_batch"], required=True)
    reserve.add_argument("--sample", action="append", required=True)
    reserve.add_argument("--batch-id")
    reserve.add_argument("--reservation-token", default=os.environ.get("EVIDENCE_RESERVATION_TOKEN"))
    _add_policy_arguments(reserve)
    adopt = sub.add_parser("adopt")
    adopt.add_argument("--run-id", required=True)
    adopt.add_argument("--action", choices=["evidence_single", "evidence_batch"], required=True)
    adopt.add_argument("--sample", action="append", required=True)
    adopt.add_argument("--batch-id")
    adopt.add_argument("--reservation-token", default=os.environ.get("EVIDENCE_RESERVATION_TOKEN"))
    adopt.add_argument("--staging", required=True, type=Path)
    adopt.add_argument("--final", required=True, type=Path)
    _add_policy_arguments(adopt)
    stage = sub.add_parser("stage")
    stage.add_argument("--id", required=True)
    stage.add_argument("--status", choices=sorted(STAGE_STATUSES), required=True)
    stage.add_argument("--message")
    stage.add_argument("--failure-type", choices=sorted(FAILURE_TYPES))
    stage.add_argument("--failed-command")
    status = sub.add_parser("status")
    status.add_argument("--value", choices=sorted(RUN_STATUSES), required=True)
    status.add_argument("--warning", action="append", default=[])
    status.add_argument("--official-v1-status", choices=["not_started", "running", "done", "failed", "cancelled"])
    status.add_argument("--evidence-v2-status", choices=sorted(RUN_STATUSES))
    status.add_argument("--failure-type", choices=sorted(FAILURE_TYPES))
    status.add_argument("--failed-stage")
    status.add_argument("--failure-message")
    status.add_argument("--failed-command")
    artifact = sub.add_parser("artifact")
    artifact.add_argument("--name", required=True)
    artifact.add_argument("--path", required=True)
    provenance = sub.add_parser("provenance")
    provenance.add_argument("--json", required=True, type=Path)
    failure_document = sub.add_parser("write-failure-evidence")
    failure_document.add_argument("--root", required=True, type=Path)
    failure_document.add_argument("--reason", required=True)
    _add_policy_arguments(failure_document)
    args = parser.parse_args()

    if args.command in {"reserve", "adopt"} and not args.reservation_token:
        parser.error("--reservation-token (or EVIDENCE_RESERVATION_TOKEN) is required")

    if args.command == "init":
        initialize_runner_state(
            args.state, args.run_id, args.action, args.sample, args.batch_id,
            _policy_from_args(args, parser),
        )
        return
    if args.command == "reserve":
        reserve_state(
            args.state, args.run_id, args.action, args.sample, args.batch_id,
            args.reservation_token, _policy_from_args(args, parser),
        )
        return
    if args.command == "adopt":
        adopt_reserved_state(
            args.state, run_id=args.run_id, action=args.action, samples=args.sample,
            batch_id=args.batch_id, reservation_token=args.reservation_token,
            staging=args.staging, final=args.final,
            policy=_policy_from_args(args, parser),
        )
        return
    if args.command == "write-failure-evidence":
        with state_lock(args.state):
            state = read_state(args.state)
            write_failure_evidence(
                state, args.root, args.reason, _policy_from_args(args, parser),
            )
        return
    with state_lock(args.state):
        state = read_state(args.state)
        if args.command == "stage":
            set_stage(state, args.id, args.status, args.message)
            if args.failure_type:
                set_failure(state, args.failure_type, args.id, args.message, args.failed_command)
            if args.status == "running":
                _validate_run_transition(state["status"], "running")
                state["status"] = "running"
                state["started_at"] = state["started_at"] or now()
        elif args.command == "status":
            _validate_run_transition(state["status"], args.value)
            state["status"] = args.value
            state["evidence_v2_status"] = args.evidence_v2_status or args.value
            if args.official_v1_status:
                state["official_v1_status"] = args.official_v1_status
            if args.failure_type:
                set_failure(state, args.failure_type, args.failed_stage, args.failure_message, args.failed_command)
            for warning in args.warning:
                if warning not in state["warnings"]:
                    state["warnings"].append(warning)
            if args.value == "running":
                state["started_at"] = state["started_at"] or now()
                state["execution_status"] = "running"
            if args.value in {"done", "done_with_warning", "blocked", "failed", "cancelled"}:
                state["finished_at"] = now()
                state["current_stage"] = None
                state["execution_status"] = "warning" if args.value == "done_with_warning" else args.value
            if args.value in {"blocked", "failed", "cancelled"}:
                state["analysis_outcome"] = "NOT_EVALUABLE"
                state["evidence_level"] = "NOT_EVALUABLE"
        elif args.command == "artifact":
            state["artifacts"][args.name] = args.path
        elif args.command == "provenance":
            with args.json.open("r", encoding="utf-8") as handle:
                state["provenance"] = json.load(handle)
        write_json_atomic(args.state, state)


if __name__ == "__main__":
    main()
