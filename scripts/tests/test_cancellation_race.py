"""Regression tests for the dashboard cancellation/Popen transition."""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from dashboard import jobs as dashboard_jobs  # noqa: E402


class FakeProcess:
    pid = 4242

    def poll(self):
        return None


class CancellationRaceTests(unittest.TestCase):
    def setUp(self):
        with dashboard_jobs.jobs_lock:
            dashboard_jobs.jobs.clear()
        self.addCleanup(self._clear)

    def _clear(self):
        with dashboard_jobs.jobs_lock:
            dashboard_jobs.jobs.clear()

    def _register(self, job_id, status="queued"):
        with dashboard_jobs.jobs_lock:
            dashboard_jobs.jobs[job_id] = {
                "status": status,
                "action": "pipeline",
                "output": [],
                "returncode": None,
            }

    def test_cancel_before_claim_prevents_process_creation(self):
        self._register("before-claim")
        request = dashboard_jobs.request_job_cancellation("before-claim")
        self.assertTrue(request["ok"])
        self.assertEqual(request["status"], "cancelled")
        self.assertFalse(
            dashboard_jobs.claim_job_for_execution("before-claim", "cmd", "log")
        )
        with patch.object(dashboard_jobs, "Popen") as popen:
            process = dashboard_jobs.launch_claimed_job(
                "before-claim", ["true"], {}
            )
        self.assertIsNone(process)
        popen.assert_not_called()

    def test_cancel_after_claim_prevents_process_creation(self):
        self._register("after-claim")
        self.assertTrue(
            dashboard_jobs.claim_job_for_execution("after-claim", "cmd", "log")
        )
        request = dashboard_jobs.request_job_cancellation("after-claim")
        self.assertTrue(request["ok"])
        with patch.object(dashboard_jobs, "Popen") as popen:
            process = dashboard_jobs.launch_claimed_job(
                "after-claim", ["true"], {}
            )
        self.assertIsNone(process)
        popen.assert_not_called()

    def test_cancel_during_popen_waits_until_process_is_registered(self):
        self._register("during-popen")
        self.assertTrue(
            dashboard_jobs.claim_job_for_execution("during-popen", "cmd", "log")
        )
        entered = threading.Event()
        release = threading.Event()
        process = FakeProcess()
        launched = []
        cancelled = []

        def controlled_popen(*_args, **_kwargs):
            entered.set()
            self.assertTrue(release.wait(timeout=3))
            return process

        with patch.object(dashboard_jobs, "Popen", side_effect=controlled_popen):
            launch_thread = threading.Thread(
                target=lambda: launched.append(
                    dashboard_jobs.launch_claimed_job(
                        "during-popen", ["true"], {}
                    )
                )
            )
            launch_thread.start()
            self.assertTrue(entered.wait(timeout=2))
            cancel_thread = threading.Thread(
                target=lambda: cancelled.append(
                    dashboard_jobs.request_job_cancellation("during-popen")
                )
            )
            cancel_thread.start()
            time.sleep(0.05)
            self.assertTrue(cancel_thread.is_alive())
            release.set()
            launch_thread.join(timeout=3)
            cancel_thread.join(timeout=3)

        self.assertEqual(launched, [process])
        self.assertIs(cancelled[0]["process"], process)
        self.assertEqual(cancelled[0]["status"], "cancelling")

    def test_running_without_registered_process_fails_closed(self):
        self._register("missing-process", status="running")
        request = dashboard_jobs.request_job_cancellation("missing-process")
        self.assertFalse(request["ok"])
        self.assertEqual(request["status"], "failed")
        with dashboard_jobs.jobs_lock:
            self.assertEqual(
                dashboard_jobs.jobs["missing-process"]["failure_type"],
                "CANCELLATION_FAILED",
            )

    def test_only_one_thread_can_claim_a_job(self):
        self._register("contended")
        barrier = threading.Barrier(8)
        claims = []

        def attempt():
            barrier.wait()
            claims.append(
                dashboard_jobs.claim_job_for_execution("contended", "cmd", "log")
            )

        threads = [threading.Thread(target=attempt) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(sum(claims), 1)

    def test_popen_failure_is_terminal(self):
        self._register("popen-failure")
        self.assertTrue(
            dashboard_jobs.claim_job_for_execution("popen-failure", "cmd", "log")
        )
        with patch.object(
            dashboard_jobs, "Popen", side_effect=OSError("simulated failure")
        ):
            with self.assertRaisesRegex(OSError, "simulated failure"):
                dashboard_jobs.launch_claimed_job(
                    "popen-failure", ["missing"], {}
                )
        with dashboard_jobs.jobs_lock:
            job = dashboard_jobs.jobs["popen-failure"]
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["failure_type"], "TOOL_FAILURE")
            self.assertIsNone(job["process"])


if __name__ == "__main__":
    unittest.main()
