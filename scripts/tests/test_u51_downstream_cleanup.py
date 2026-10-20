"""U-51-b3r: SIGTERM removes temporary files of the downstream evidence steps."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _terminate(script: str, prefix: str, args: list[str], tmp_path: Path):
    env = dict(os.environ, TMPDIR=str(tmp_path))
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "evidence" / script), *args],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not list(tmp_path.glob(prefix)) and time.monotonic() < deadline:
            if process.poll() is not None:
                _stdout, stderr = process.communicate(timeout=5)
                raise AssertionError(stderr.decode()[-2000:])
            time.sleep(0.05)
        assert list(tmp_path.glob(prefix))
        os.killpg(process.pid, signal.SIGTERM)
        _stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 143, stderr.decode()
        assert not list(tmp_path.glob(prefix))
        assert "SIGTERM" in stderr.decode()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


@pytest.mark.skipif(os.name != "posix", reason="Sinais POSIX")
def test_loci_removes_temp_on_sigterm(tmp_path):
    fifo = tmp_path / "fragments.tsv"
    os.mkfifo(fifo)
    out = tmp_path / "locus_evidence.tsv"
    _terminate(
        "build_loci.py",
        "genein-loci-*",
        ["--fragments", str(fifo), "--work-dir", str(tmp_path), "--out", str(out)],
        tmp_path,
    )
    assert not out.exists()


@pytest.mark.skipif(os.name != "posix", reason="Sinais POSIX")
def test_hsp_removes_temp_on_sigterm(tmp_path):
    fifo = tmp_path / "hits.tsv"
    os.mkfifo(fifo)
    out = tmp_path / "hsp_evidence.tsv"
    loci = tmp_path / "loci.tsv"
    loci.write_text("locus_id\n", encoding="utf-8")
    _terminate(
        "build_hsp_evidence.py",
        "genein-hsp-ids-*",
        ["--blast", f"blastn={fifo}", "--loci", str(loci), "--work-dir", str(tmp_path), "--out", str(out)],
        tmp_path,
    )
    assert not out.exists()


@pytest.mark.skipif(os.name != "posix", reason="Sinais POSIX")
def test_competitive_removes_temp_on_sigterm(tmp_path):
    fifo = tmp_path / "fragments.tsv"
    os.mkfifo(fifo)
    out = tmp_path / "competitive_hits.tsv"
    _terminate(
        "competitive_hits.py",
        "genein-competitive-*",
        ["--fragments", str(fifo), "--work-dir", str(tmp_path), "--out", str(out)],
        tmp_path,
    )
    assert not out.exists()
