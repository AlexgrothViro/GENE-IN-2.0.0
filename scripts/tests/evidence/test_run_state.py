import sys
import json
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from run_state import (
    adopt_reserved_state, initial_state, initialize_runner_state, reserve_state,
    set_failure, set_stage, state_lock,
)
from common import write_json_atomic


class RunStateTests(unittest.TestCase):
    def test_terminal_stage_cannot_regress_to_failed(self):
        state = initial_state("run-safe", "evidence_single", ["sample"], None)
        set_stage(state, "quality_control", "done", "QC concluído")
        set_stage(state, "quality_control", "running", "handoff repetido")
        self.assertEqual(state["stages"][1]["status"], "done")
        with self.assertRaises(ValueError):
            set_stage(state, "quality_control", "failed", "não deve regredir")

    def test_failure_metadata_is_typed_and_keeps_official_status_separate(self):
        state = initial_state("run-safe", "evidence_single", ["sample"], None)
        state["official_v1_status"] = "done"
        set_failure(state, "DEPENDENCY_MISSING", "input_validation", "ferramenta ausente", "command -v blastn")
        self.assertEqual(state["official_v1_status"], "done")
        self.assertEqual(state["failure_type"], "DEPENDENCY_MISSING")
        self.assertEqual(state["failed_stage"], "input_validation")
        self.assertEqual(state["failed_command"], "command -v blastn")

    def test_official_pipeline_and_v2_statuses_do_not_get_mixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps(initial_state("run-safe", "evidence_single", ["sample"], None)), encoding="utf-8")
            runner = [sys.executable, str(ROOT / "scripts/evidence/run_state.py"), "--state", str(state_path)]
            subprocess.run(runner + ["status", "--value", "running", "--official-v1-status", "running", "--evidence-v2-status", "queued"], check=True)
            subprocess.run(runner + ["stage", "--id", "quality_control", "--status", "running"], check=True)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["official_v1_status"], "running")
            self.assertEqual(state["evidence_v2_status"], "queued")
            subprocess.run(runner + ["status", "--value", "running", "--official-v1-status", "done", "--evidence-v2-status", "running"], check=True)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["official_v1_status"], "done")
            self.assertEqual(state["evidence_v2_status"], "running")

    def test_dashboard_reservation_is_adopted_only_with_matching_identity_and_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state/run-safe.json"
            staging = root / ".staging/run-safe"
            final = root / "runs/run-safe"
            token = "reservation-token-0123456789abcdef"
            reserve_state(state_path, "run-safe", "evidence_single", ["sample-a"], None, token)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "running"
            state["official_v1_status"] = "done"
            state["evidence_v2_status"] = "running"
            set_stage(state, "input_validation", "done", None)
            set_stage(state, "quality_control", "done", None)
            set_stage(state, "assembly", "done", None)
            set_stage(state, "initial_blast", "done", None)
            state_path.write_text(json.dumps(state), encoding="utf-8")
            adopted = adopt_reserved_state(
                state_path, run_id="run-safe", action="evidence_single", samples=["sample-a"],
                batch_id=None, reservation_token=token, staging=staging, final=final,
            )
            self.assertEqual(adopted["reservation"]["status"], "claimed")
            with self.assertRaises(FileExistsError):
                adopt_reserved_state(
                    state_path, run_id="run-safe", action="evidence_single", samples=["sample-a"],
                    batch_id=None, reservation_token=token, staging=staging, final=final,
                )

    def test_two_concurrent_adopters_cannot_claim_the_same_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state/run-safe.json"
            staging = root / ".staging/run-safe"
            final = root / "runs/run-safe"
            token = "reservation-token-0123456789abcdef"
            reserve_state(state_path, "run-safe", "evidence_single", ["sample-a"], None, token)

            def attempt():
                return adopt_reserved_state(
                    state_path, run_id="run-safe", action="evidence_single", samples=["sample-a"],
                    batch_id=None, reservation_token=token, staging=staging, final=final,
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(attempt) for _ in range(2)]
            successes = sum(future.exception() is None for future in futures)
            self.assertEqual(successes, 1)

    def test_existing_successful_run_and_previous_state_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state/run-safe.json"
            final = root / "runs/run-safe"
            final.mkdir(parents=True)
            (final / "SUCCESS.json").write_text('{"status":"done"}\n', encoding="utf-8")
            token = "reservation-token-0123456789abcdef"
            reserve_state(state_path, "run-safe", "evidence_single", ["sample-a"], None, token)
            original = state_path.read_bytes()
            with self.assertRaises(FileExistsError):
                adopt_reserved_state(
                    state_path, run_id="run-safe", action="evidence_single", samples=["sample-a"],
                    batch_id=None, reservation_token=token, staging=root / ".staging/run-safe", final=final,
                )
            with self.assertRaises(FileExistsError):
                initialize_runner_state(state_path, "run-safe", "evidence_single", ["sample-a"], None)
            self.assertEqual(state_path.read_bytes(), original)

    def test_terminal_run_cannot_regress_to_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(initial_state("run-safe", "evidence_single", ["sample"], None)),
                encoding="utf-8",
            )
            runner = [
                sys.executable, str(ROOT / "scripts/evidence/run_state.py"),
                "--state", str(state_path),
            ]
            subprocess.run(
                runner + ["status", "--value", "failed", "--failure-type", "TOOL_FAILURE"],
                check=True,
            )
            result = subprocess.run(
                runner + ["status", "--value", "running"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8"))["status"],
                "failed",
            )

    def test_concurrent_artifact_updates_are_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state = initial_state("run-safe", "evidence_single", ["sample"], None)
            state["status"] = "running"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            runner = [
                sys.executable, str(ROOT / "scripts/evidence/run_state.py"),
                "--state", str(state_path), "artifact",
            ]

            def update(index):
                return subprocess.run(
                    runner + ["--name", f"artifact-{index}", "--path", f"path-{index}"],
                    capture_output=True, text=True,
                )

            with ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(update, range(30)))
            failures = [
                result.stderr for result in results if result.returncode != 0
            ]
            self.assertFalse(failures, "\n".join(failures))
            final = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(final["artifacts"]), 30)

    def test_abandoned_state_lock_is_recoverable_after_stale_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            lock_dir = state_path.parent / ".locks" / f"{state_path.name}.lock"
            lock_dir.mkdir(parents=True)
            (lock_dir / "owner.json").write_text('{"token":"abandoned"}\n', encoding="utf-8")
            old = time.time() - 10
            import os
            os.utime(lock_dir, (old, old))
            with state_lock(
                state_path, timeout_seconds=1, stale_after_seconds=0.1,
            ):
                self.assertTrue(lock_dir.is_dir())
            self.assertFalse(lock_dir.exists())

    def test_adoption_cannot_overwrite_cancellation_waiting_on_state_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state/run-safe.json"
            token = "reservation-token-" + "x" * 32
            reserve_state(
                state_path, "run-safe", "evidence_single", ["sample-a"], None, token,
            )
            staging = root / ".staging/run-safe"
            final = root / "runs/run-safe"
            result = {}

            def adopt():
                try:
                    adopt_reserved_state(
                        state_path, run_id="run-safe", action="evidence_single",
                        samples=["sample-a"], batch_id=None, reservation_token=token,
                        staging=staging, final=final,
                    )
                except Exception as exc:
                    result["error"] = exc

            with state_lock(state_path):
                worker = threading.Thread(target=adopt)
                worker.start()
                claim = state_path.parent / ".claims" / f"{state_path.name}.claim"
                deadline = time.monotonic() + 2
                while not claim.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["status"] = "cancelled"
                state["evidence_v2_status"] = "cancelled"
                write_json_atomic(state_path, state)
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertIsInstance(result.get("error"), FileExistsError)
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8"))["status"],
                "cancelled",
            )


if __name__ == "__main__":
    unittest.main()
