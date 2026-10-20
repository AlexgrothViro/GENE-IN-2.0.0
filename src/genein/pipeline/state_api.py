"""In-process adapter over scripts/evidence/run_state.py's existing state machine.

Batch orchestration used to shell out to run_state.py for every state
transition. This module calls the same functions the CLI calls, in the same
process, so the on-disk contract (transitions, fields, locking, reservation
tokens) is identical without spawning a subprocess per mutation.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_MODULE_CACHE: dict[str, object] = {}


def load_run_state(scripts_dir: Path):
    """Import run_state.py the same way scripts/dashboard/jobs.py does: as a
    bare top-level module, with its own directory placed on sys.path so its
    sibling imports (common, activation_policy, evidence_contract) resolve.

    Keyed by the resolved scripts directory so a checkout-local caller never
    silently accepts a module cached from a different checkout: since Python
    caches imports globally under the bare name "run_state", a module already
    imported from another location earlier in the process would otherwise win
    over the requested scripts_dir.
    """
    resolved_dir = Path(scripts_dir).resolve()
    key = str(resolved_dir)
    module = _MODULE_CACHE.get(key)
    if module is not None:
        return module
    path = str(scripts_dir)
    if path not in sys.path:
        sys.path.insert(0, path)
    module = importlib.import_module("run_state")
    module_dir = Path(module.__file__).resolve().parent
    if module_dir != resolved_dir:
        raise RuntimeError(
            "run_state module already loaded from a different checkout: "
            f"expected {resolved_dir}, got {module_dir}"
        )
    _MODULE_CACHE[key] = module
    return module


class RunStateApi:
    """Mirrors run_state.py's CLI subcommands as direct function calls."""

    def __init__(self, scripts_dir: Path, policy_path: Path, profiles_path: Path):
        self.rs = load_run_state(scripts_dir)
        self.policy_path = policy_path
        self.profiles_path = profiles_path

    def _policy(self) -> dict:
        return self.rs.load_public_activation_policy(
            self.policy_path, profiles_path=self.profiles_path,
        )

    def init(self, state_file: Path, run_id: str, action: str,
             samples: list[str], batch_id: str | None) -> dict:
        return self.rs.initialize_runner_state(
            state_file, run_id, action, samples, batch_id, self._policy(),
        )

    def adopt(self, state_file: Path, *, run_id: str, action: str,
              samples: list[str], batch_id: str | None, reservation_token: str,
              staging: Path, final: Path) -> dict:
        return self.rs.adopt_reserved_state(
            state_file, run_id=run_id, action=action, samples=samples,
            batch_id=batch_id, reservation_token=reservation_token,
            staging=staging, final=final, policy=self._policy(),
        )

    def stage(self, state_file: Path, stage_id: str, status: str,
              message: str | None = None, *, failure_type: str | None = None,
              failed_command: str | None = None) -> dict:
        rs = self.rs

        def mutator(state: dict) -> None:
            rs.set_stage(state, stage_id, status, message)
            if failure_type:
                rs.set_failure(state, failure_type, stage_id, message, failed_command)
            if status == "running":
                # Same run-status bump the CLI's "stage" subcommand performs.
                rs._validate_run_transition(state["status"], "running")
                state["status"] = "running"
                state["started_at"] = state["started_at"] or rs.now()

        return rs.mutate_state_file(state_file, mutator)

    def status(self, state_file: Path, value: str, *, failure_type: str | None = None,
               failed_stage: str | None = None, failure_message: str | None = None,
               failed_command: str | None = None, warnings: tuple[str, ...] = (),
               official_v1_status: str | None = None,
               evidence_v2_status: str | None = None) -> dict:
        rs = self.rs

        def mutator(state: dict) -> None:
            rs._validate_run_transition(state["status"], value)
            state["status"] = value
            state["evidence_v2_status"] = evidence_v2_status or value
            if official_v1_status:
                state["official_v1_status"] = official_v1_status
            if failure_type:
                rs.set_failure(state, failure_type, failed_stage, failure_message, failed_command)
            for warning in warnings:
                if warning not in state["warnings"]:
                    state["warnings"].append(warning)
            if value == "running":
                state["started_at"] = state["started_at"] or rs.now()
                state["execution_status"] = "running"
            if value in {"done", "done_with_warning", "blocked", "failed", "cancelled"}:
                state["finished_at"] = rs.now()
                state["current_stage"] = None
                state["execution_status"] = "warning" if value == "done_with_warning" else value
            if value in {"blocked", "failed", "cancelled"}:
                state["analysis_outcome"] = "NOT_EVALUABLE"
                state["evidence_level"] = "NOT_EVALUABLE"

        return rs.mutate_state_file(state_file, mutator)

    def write_failure_evidence(self, state_file: Path, root: Path, reason: str) -> None:
        rs = self.rs
        with rs.state_lock(state_file):
            state = rs.read_state(state_file)
            rs.write_failure_evidence(state, root, reason, self._policy())
