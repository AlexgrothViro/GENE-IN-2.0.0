import importlib.util
import json
import os
import signal
import sys
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from common import write_json_atomic
from evidence_dashboard import EvidenceDashboardService
import index_cache
from run_state import initial_state

spec = importlib.util.spec_from_file_location("gene_in_ux_dashboard", ROOT / "scripts" / "ux_dashboard.py")
ux_dashboard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ux_dashboard)


class PendingGapRegressionTests(unittest.TestCase):
    def test_index_reuse_blocked_on_content_change_same_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            reference = Path(tmp) / "panel.fa"
            reference.write_text(">ref\nAAAA\n", encoding="utf-8")
            timestamp = reference.stat().st_mtime_ns
            identity = {"makeblastdb": {"command": "makeblastdb", "executable": "/tool", "version": "1", "sha256": "a"}}
            with patch.object(index_cache, "builder_identity", side_effect=lambda name: identity[name]):
                manifest = index_cache.fingerprint(reference, ["makeblastdb"])
                reference.write_text(">ref\nTTTT\n", encoding="utf-8")
                os.utime(reference, ns=(timestamp, timestamp))
                self.assertFalse(index_cache.matches(manifest, reference, ["makeblastdb"]))
            manager = (ROOT / "scripts" / "ops" / "db_manager.sh").read_text(encoding="utf-8")
            self.assertNotIn('-ot "$REF_FASTA"', manager)
            self.assertIn("index_cache.py", manager)

    def test_no_output_path_bypasses_legacy_incompatibility_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = EvidenceDashboardService(root)
            run_id = "run-public"
            state_path = root / "results/evidence/state" / f"{run_id}.json"
            state = initial_state(run_id, "evidence_single", ["sample-a"], None)
            state["status"] = "done"
            state["pipeline_version"] = "2.0.0-alpha.1"
            write_json_atomic(state_path, state)
            run_dir = root / "results/evidence/runs" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "SUCCESS.json").write_text('{"status":"done"}\n', encoding="utf-8")
            (run_dir / "sample_evidence.json").write_text(json.dumps({"sample_id": "sample-a", "evidence_class": "STRONG"}), encoding="utf-8")
            legacy_report = root / "results/reports/sample-a_summary.md"
            legacy_report.parent.mkdir(parents=True, exist_ok=True)
            legacy_report.write_text("LEGACY_STRONG_RAW_REPORT", encoding="utf-8")
            result = service.result(run_id)
            self.assertFalse(result["valid_alpha2"])
            self.assertEqual(result["compatibility"]["status"], "LEGACY_INCOMPATIBLE")
            self.assertEqual(result["compatibility"]["analysis_outcome"], "NOT_EVALUABLE")
            self.assertIn("reexecute", result["compatibility"]["message"])
            self.assertIsNone(result["evidence_v2"])
            self.assertNotEqual(result.get("evidence_level"), "E1")
            self.assertTrue(result["artifacts_preserved"])
            with self.assertRaisesRegex(ValueError, "NOT_EVALUABLE"):
                service.artifact(run_id, "sample_evidence")

    def test_dashboard_reports_cancellation_group_kill_failure_as_failed_not_success(self):
        class BrokenProcess:
            pid = 1

            def send_signal(self, _signal):
                raise OSError("simulated signal failure")

        with patch.object(ux_dashboard.os, "name", "nt"):
            ok, error = ux_dashboard.terminate_process_group(BrokenProcess(), 1)
        self.assertFalse(ok)
        self.assertIn("could not signal", error)
        job_id = "cancel-failure-test"
        with ux_dashboard.jobs_lock:
            ux_dashboard.jobs[job_id] = {"status": "cancelling", "action": "pipeline"}
        try:
            ux_dashboard.mark_cancellation_failure(job_id, "pipeline", "simulated")
            self.assertEqual(ux_dashboard.jobs[job_id]["status"], "failed")
            self.assertEqual(ux_dashboard.jobs[job_id]["failure_type"], "CANCELLATION_FAILED")
        finally:
            with ux_dashboard.jobs_lock:
                ux_dashboard.jobs.pop(job_id, None)

    def test_queued_cancellation_cannot_be_overwritten_by_job_start(self):
        job_id = "queued-cancel-test"
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with ux_dashboard.jobs_lock:
                ux_dashboard.jobs[job_id] = {
                    "status": "cancelling", "action": "pipeline", "output": [],
                }
            try:
                with (
                    patch.object(ux_dashboard, "REPO_ROOT", temp_root),
                    patch.object(ux_dashboard, "LOG_DIR", temp_root / "logs"),
                    patch.object(ux_dashboard, "RUNS_DIR", temp_root / "runs"),
                    patch.object(
                        ux_dashboard, "build_command",
                        return_value=([sys.executable, "-c", "print('should not run')"], {}),
                    ),
                    patch.object(ux_dashboard, "Popen") as popen,
                ):
                    ux_dashboard.run_job(job_id, "pipeline", {"sample": "sample-a"})
                popen.assert_not_called()
                self.assertEqual(ux_dashboard.jobs[job_id]["status"], "cancelled")
            finally:
                with ux_dashboard.jobs_lock:
                    ux_dashboard.jobs.pop(job_id, None)

    def test_force_terminal_state_is_not_evaluable_and_is_locked(self):
        run_id = "terminal-state-test"
        with tempfile.TemporaryDirectory() as tmp:
            evidence_root = Path(tmp)
            state_path = evidence_root / "state" / f"{run_id}.json"
            write_json_atomic(
                state_path,
                initial_state(run_id, "evidence_single", ["sample-a"], None),
            )
            with patch.object(ux_dashboard.EVIDENCE_SERVICE, "evidence_root", evidence_root):
                ux_dashboard.force_evidence_state_terminal(
                    run_id, "failed", "simulated", "TOOL_FAILURE",
                )
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["execution_status"], "failed")
            self.assertEqual(state["analysis_outcome"], "NOT_EVALUABLE")
            self.assertEqual(state["evidence_level"], "NOT_EVALUABLE")

    def test_windows_signal_value_error_is_reported_not_raised(self):
        class InvalidSignalProcess:
            pid = 1

            def send_signal(self, _signal):
                raise ValueError("unsupported signal")

        with patch.object(ux_dashboard.os, "name", "nt"):
            ok, error = ux_dashboard.terminate_process_group(InvalidSignalProcess(), 999)
        self.assertFalse(ok)
        self.assertIn("unsupported signal", error)

    @unittest.skipIf(os.name == "nt", "POSIX process-group semantics")
    def test_cancellation_reaches_spawned_child_process(self):
        script = (
            "import subprocess,sys,time;"
            "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
            "print(child.pid,flush=True);time.sleep(60)"
        )
        parent = subprocess.Popen(
            [sys.executable, "-u", "-c", script],
            stdout=subprocess.PIPE, text=True, start_new_session=True,
        )
        child_pid = int(parent.stdout.readline().strip())
        try:
            ok, error = ux_dashboard.terminate_process_group(parent, signal.SIGTERM)
            self.assertTrue(ok, error)
            parent.wait(timeout=5)
            deadline = time.monotonic() + 5
            child_state = None
            while time.monotonic() < deadline:
                try:
                    child_state = Path(f"/proc/{child_pid}/stat").read_text().split()[2]
                except (FileNotFoundError, ProcessLookupError):
                    # O filho pode morrer entre o open e o read: ESRCH também
                    # significa que a cancelamento alcançou o processo.
                    child_state = None
                if child_state in {None, "Z"}:
                    break
                time.sleep(0.05)
            self.assertIn(child_state, {None, "Z"})
        finally:
            if parent.poll() is None:
                os.killpg(os.getpgid(parent.pid), signal.SIGKILL)
                parent.wait(timeout=5)
            if parent.stdout is not None:
                parent.stdout.close()

    def test_dashboard_responses_disable_stale_cache(self):
        class Handler:
            def __init__(self):
                self.headers = {}

            def send_response(self, status):
                self.status = status

            def send_header(self, key, value):
                self.headers[key] = value

            def end_headers(self):
                pass

            class Stream:
                @staticmethod
                def write(_data):
                    return None

            wfile = Stream()

        handler = Handler()
        ux_dashboard.json_response(handler, 200, {"run_id": "new"})
        self.assertEqual(handler.headers["Cache-Control"], "no-cache, no-store, must-revalidate")
        self.assertEqual(handler.headers["Pragma"], "no-cache")
        api = (ROOT / "dashboard" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn('cache: "no-store"', api)


if __name__ == "__main__":
    unittest.main()
