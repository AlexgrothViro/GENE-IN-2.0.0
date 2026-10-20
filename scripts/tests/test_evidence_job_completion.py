"""The live job must respect its own persisted result after cancellation."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from dashboard import jobs
from dashboard.handler import DashboardHandler
from evidence_dashboard import EvidenceDashboardService
from run_state import initial_state


class EvidenceJobCompletionTests(unittest.TestCase):
    run_id = "completion-run"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.service = EvidenceDashboardService(self.root)
        self.state_path = self.service.evidence_root / "state" / f"{self.run_id}.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(jobs.jobs.clear)
        jobs.jobs.clear()
        for name, value in (
            ("get_evidence_service", Mock(return_value=self.service)),
            ("LOG_DIR", self.root),
            ("build_command", Mock(return_value=(["controlled-process"], {}))),
        ):
            patcher = patch.object(jobs, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def state(self, status):
        state = initial_state(self.run_id, "evidence_batch", ["sample-a"], "batch-a")
        state.update(status=status, evidence_v2_status=status, official_v1_status="done")
        if status in {"failed", "blocked", "cancelled"}:
            state.update(failure_type="CANCELLED" if status == "cancelled" else "TOOL_FAILURE",
                         failure_message="persisted reason", analysis_outcome="NOT_EVALUABLE")
        return state

    def execute(self, state, rc=130, cancel=True, action="evidence_batch"):
        if state is not None:
            payload = state if isinstance(state, bytes) else json.dumps(state).encode()
            self.state_path.write_bytes(payload)
        jobs.jobs[self.run_id] = {"status": "queued", "action": action, "output": []}
        process = SimpleNamespace(stdout=io.StringIO(""), returncode=rc)

        def wait():
            if cancel:
                self.assertTrue(jobs.request_job_cancellation(self.run_id)["ok"])
            return rc

        process.wait = wait
        with patch.object(jobs, "Popen", return_value=process):
            jobs.run_job(self.run_id, action, {"run_id": self.run_id, "sample": "sample-a"})
        job = jobs.jobs[self.run_id]
        self.assertEqual(job["exit_code"], rc)
        self.assertIsNone(job["process"])
        self.assertTrue(job["finished_at"])
        return job

    def response(self):
        handler = SimpleNamespace(
            path=f"/api/job/{self.run_id}", wfile=io.BytesIO(),
            send_response=Mock(), send_header=Mock(), end_headers=Mock(),
        )
        DashboardHandler._do_GET_inner(handler)
        handler.send_response.assert_called_once_with(200)
        return json.loads(handler.wfile.getvalue())

    def test_resource_signal_refines_failed_state_and_live_api(self):
        for rc, expected in ((137, 'PROCESS_KILLED'), (143, 'PROCESS_TERMINATED')):
            with self.subTest(rc=rc):
                job = self.execute(self.state('failed'), rc=rc, cancel=False)
                self.assertEqual(job['failure_type'], expected)
                self.assertEqual(self.response()['failure_type'], expected)
                persisted = json.loads(self.state_path.read_text())
                self.assertEqual(persisted['failure_type'], expected)
                self.assertIn('SIG', persisted['failure_message'])

    def test_external_sigterm_is_not_user_cancellation(self):
        job = self.execute(self.state('cancelled'), rc=-15, cancel=False)
        self.assertEqual(job['failure_type'], 'PROCESS_TERMINATED')
        self.assertEqual(self.response()['failure_type'], 'PROCESS_TERMINATED')
        self.assertEqual(json.loads(self.state_path.read_text())['status'], 'failed')

    def test_committed_cancellation_is_done_in_live_api_and_preserves_state(self):
        for action in ("evidence_batch", "evidence_pipeline"):
            for status in ("done", "done_with_warning"):
                for rc in (0, 130):
                    with self.subTest(action=action, status=status, rc=rc):
                        state = self.state(status)
                        job = self.execute(state, rc=rc, action=action)
                        self.assertEqual(job["status"], "done")
                        self.assertIsNone(job["failure_type"])
                        self.assertIsNone(job["failure_message"])
                        payload = self.response()
                        self.assertEqual(payload["status"], "done")
                        self.assertEqual(payload["evidence_v2_status"], status)
                        self.assertEqual(self.state_path.read_bytes(), json.dumps(state).encode())

    def test_terminal_cancellation_failure_and_block_are_not_overwritten(self):
        for status in ("cancelled", "failed", "blocked"):
            with self.subTest(status=status):
                state = self.state(status)
                job = self.execute(state)
                self.assertEqual(job["status"], status)
                self.assertEqual(job["failure_type"], state["failure_type"])
                self.assertEqual(job["failure_message"], "persisted reason")
                self.assertEqual(self.response()["status"], status)
                self.assertEqual(self.state_path.read_bytes(), json.dumps(state).encode())

    def test_cancel_before_promotion_terminalizes_running_state(self):
        job = self.execute(self.state("running"))
        self.assertEqual(job["status"], "cancelled")
        self.assertEqual(json.loads(self.state_path.read_bytes())["status"], "cancelled")

    def test_unusable_or_foreign_state_cannot_report_success(self):
        cases = [None, b"{", b"\xff", [], b"null", {},
                 {**self.state("done"), "run_id": "different-run"},
                 {**self.state("done"), "stages": None},
                 {**self.state("done"), "status": []},
                 {**self.state("done"), "evidence_v2_status": []},
                 {**self.state("done"), "status": "unknown"},
                 {**self.state("done"), "evidence_v2_status": "failed"},
                 {**self.state("running"), "evidence_v2_status": "done"}]
        for index, state in enumerate(cases):
            for rc in (0, 130):
                with self.subTest(case=index, rc=rc):
                    self.state_path.unlink(missing_ok=True)
                    job = self.execute(state, rc=rc)
                    self.assertEqual(job["status"], "failed" if rc == 0 else "cancelled")
                    self.assertNotEqual(self.response()["status"], "done")
                    if state is not None and not (isinstance(state, dict) and state.get("status") == "running"):
                        expected = state if isinstance(state, bytes) else json.dumps(state).encode()
                        self.assertEqual(self.state_path.read_bytes(), expected)

    def test_normal_failure_remains_failed(self):
        job = self.execute(self.state("failed"), rc=23, cancel=False)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["failure_type"], "TOOL_FAILURE")

    def test_non_evidence_cancellation_keeps_existing_return_code_behavior(self):
        for rc, expected in ((0, "failed"), (130, "cancelled")):
            with self.subTest(rc=rc):
                job = self.execute(self.state("done"), rc=rc, action="pipeline")
                self.assertEqual(job["status"], expected)

    def test_normal_success_uses_same_v2_summary(self):
        job = self.execute(self.state("done_with_warning"), rc=0, cancel=False)
        self.assertEqual(job["status"], "done")
        self.assertEqual(self.response()["evidence_v2_status"], "done_with_warning")


if __name__ == "__main__":
    unittest.main()
