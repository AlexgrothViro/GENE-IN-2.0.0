"""U-49-b3: SIGTERM removes the HSP aggregation temporary directory."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name != "posix", reason="Sinais POSIX")
def test_aggregate_removes_temp_on_sigterm(tmp_path):
    fifo = tmp_path / "hits.tsv"
    os.mkfifo(fifo)
    out = tmp_path / "fragment_evidence.tsv"
    env = dict(os.environ, TMPDIR=str(tmp_path))
    process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "evidence" / "aggregate_hsps.py"),
            "--blast", f"blastn={fifo}",
            "--work-dir", str(tmp_path),
            "--out", str(out),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not list(tmp_path.glob("genein-hsps-*")) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert list(tmp_path.glob("genein-hsps-*"))
        os.killpg(process.pid, signal.SIGTERM)
        _stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 143, stderr
        assert not list(tmp_path.glob("genein-hsps-*"))
        assert not out.exists()
        assert "SIGTERM" in stderr.decode()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
