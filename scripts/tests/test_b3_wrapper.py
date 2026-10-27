import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import time
import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name != 'posix', reason='Wrapper Linux')
@pytest.mark.parametrize('wrapper', ['bundle/run.sh', 'run_linux.sh'])
def test_wrapper_without_make_is_actionable(tmp_path, wrapper):
    for tool in ('bash', 'dirname', 'uname'):
        (tmp_path/tool).symlink_to(shutil.which(tool))
    result = subprocess.run([shutil.which('bash'), str(ROOT/wrapper), 'test-env'], env=dict(os.environ, PATH=str(tmp_path)), capture_output=True, text=True)
    assert result.returncode == 2
    assert 'make não encontrado' in result.stderr
    assert 'bash bundle/install_wsl.sh' in result.stderr
    assert 'exec: make' not in result.stderr


def test_wrapper_forwards_interrupt_to_the_child_tree():
    text = (ROOT / "bundle/run.sh").read_text(encoding="utf-8")
    assert "genein_run_tree" in text
    assert "CANCELADO" in text
    assert "setsid" in text
    assert '"$@" <&0 &' in text
    assert "GENEIN_CANCEL_WAIT" in text
    assert "genein_child_running" in text
    assert 'exec "$MICRO" run -p "$ENV_DIR" python -m genein' not in text
    assert 'exec "$MICRO" run -p "$ENV_DIR" make' not in text
    stop = text[text.index("genein_stop_tree"): text.index("trap genein_stop_tree")]
    assert "sleep 2" not in stop


def _fake_bundle(tmp_path: Path, micromamba_body: str) -> Path:
    bundle = tmp_path / "gene-in-bundle"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "env").mkdir()
    micromamba = bundle / "bin" / "micromamba"
    micromamba.write_text(micromamba_body, encoding="utf-8")
    micromamba.chmod(micromamba.stat().st_mode | stat.S_IEXEC)
    return bundle


@pytest.mark.skipif(os.name != "posix", reason="Wrapper Linux")
def test_wrapper_background_child_keeps_caller_stdin(tmp_path):
    seen = tmp_path / "stdin.txt"
    bundle = _fake_bundle(tmp_path, f"""#!/bin/sh
cat > '{seen}'
exit 0
""")
    env = os.environ.copy()
    env["GENEIN_BUNDLE_DIR"] = str(bundle)
    result = subprocess.run(
        ["bash", str(ROOT / "bundle/run.sh"), "genein", "ignored"],
        env=env, input="payload-from-caller\n", text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen.read_text(encoding="utf-8") == "payload-from-caller\n"


@pytest.mark.skipif(os.name != "posix", reason="Wrapper Linux")
def test_wrapper_interrupt_waits_for_slow_cancelled_receipt(tmp_path):
    receipt = tmp_path / "execution.json"
    ready = tmp_path / "ready"
    bundle = _fake_bundle(tmp_path, f"""#!/usr/bin/env python3
import json, os, signal, time
from pathlib import Path
receipt = Path({str(receipt)!r})
ready = Path({str(ready)!r})
receipt.write_text(json.dumps({{"status": "running"}}), encoding="utf-8")
ready.write_text("1", encoding="utf-8")
def cancel(*_args):
    time.sleep(float(os.environ.get("GENEIN_TEST_SLOW_CANCEL", "3")))
    receipt.write_text(json.dumps({{"status": "cancelled", "exit_code": 130}}), encoding="utf-8")
    raise SystemExit(130)
signal.signal(signal.SIGINT, cancel)
signal.signal(signal.SIGTERM, cancel)
time.sleep(90)
""")
    env = os.environ.copy()
    env["GENEIN_BUNDLE_DIR"] = str(bundle)
    env["GENEIN_CANCEL_WAIT"] = "15"
    env["GENEIN_TEST_SLOW_CANCEL"] = "3"
    process = subprocess.Popen(
        ["bash", str(ROOT / "bundle/run.sh"), "genein"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert process.poll() is None, (process.stderr.read() if process.stderr else "")
            assert time.monotonic() < deadline
            time.sleep(0.05)
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=20) == 130
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    stderr = process.stderr.read() if process.stderr else ""
    assert "CANCELADO" in stderr
    record = json.loads(receipt.read_text(encoding="utf-8"))
    assert record["status"] == "cancelled"
    assert record["exit_code"] == 130
