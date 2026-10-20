"""Private sample boundary and lifecycle of processes owned by the batch.

Stage/state/configuration logic still belongs to the existing shell adapters.
The sample entrypoint has no batch dispatch, and uses exactly the same setup
and stages as scripts/pipeline/run.sh.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import time


class BatchCancelled(Exception):
    """Cancellation observed at an orchestration boundary."""


class ProcessRunner:
    """Own each command's process group, including grandchildren on cancellation.

    Shell stages require POSIX. A handler only records intent, so a signal
    between Popen and registration cannot strand a process. State cleanup and
    the final commit are allowed to finish without asynchronous interruption.
    """

    def __init__(self, env: dict[str, str]):
        self.env = env
        self.cancelled = False

    def checkpoint(self) -> None:
        if self.cancelled:
            raise BatchCancelled()

    @contextmanager
    def signals(self):
        def cancel(_signum, _frame):
            self.cancelled = True

        previous = {sig: signal.signal(sig, cancel) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            yield
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    @staticmethod
    def _stop_group(process: subprocess.Popen) -> None:
        # The leader may already have exited while a tool/tee is still alive.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            process.poll()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()

    def run(self, command, *, env=None, capture=False, allow_cancel=True) -> str:
        if allow_cancel:
            self.checkpoint()
        process = subprocess.Popen(
            [str(arg) for arg in command], env=self.env if env is None else env,
            start_new_session=True, text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        try:
            while True:
                if allow_cancel:
                    self.checkpoint()
                try:
                    stdout, _ = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if allow_cancel:
                self.checkpoint()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, command)
            return (stdout or "").strip()
        except BaseException:
            self._stop_group(process)
            raise


def execute_sample(*, repo_root: Path, row: dict[str, str], run_id: str,
                   profiles: Path, evidence_root: Path, threads: str,
                   runner: ProcessRunner, options: list[str] | tuple[str, ...] = ()) -> None:
    env = dict(runner.env)
    env.update({
        "SAMPLE_R1": row["r1"], "SAMPLE_R2": row["r2"],
        "SAMPLE_SINGLE": "", "CONTIGS": "",
        "EVIDENCE_LIBRARY_MODE": row["library_mode"], "EVIDENCE_UMI_MODE": row["umi_mode"],
        "EVIDENCE_ROLE": row["role"], "EVIDENCE_EXPECTED_TARGET": row["expected_target"],
        "EVIDENCE_RUN_ID": run_id, "EVIDENCE_BATCH_ID": row["batch_id"],
        # A dashboard reservation belongs only to the parent, never its children.
        "EVIDENCE_RESERVATION_TOKEN": "",
    })
    runner.run([
        "bash", repo_root / "scripts/pipeline/run_sample.sh",
        "--sample", row["sample_id"], "--r1", row["r1"], "--r2", row["r2"],
        "--threads", threads, "--evidence-v2",
        "--evidence-profiles", profiles, "--evidence-root", evidence_root, *options,
    ], env=env)
