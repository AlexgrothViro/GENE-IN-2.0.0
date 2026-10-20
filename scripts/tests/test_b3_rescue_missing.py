import subprocess
import sys
from pathlib import Path


def test_missing_raw_fails_but_empty_raw_is_valid(tmp_path):
    script = Path(__file__).resolve().parents[2] / 'scripts/pipeline/filter_rescue_reads.py'
    raw, output = tmp_path/'raw.tsv', tmp_path/'out.tsv'
    command = [sys.executable, str(script), '--blast-raw', str(raw), '--out-tsv', str(output)]
    missing = subprocess.run(command, capture_output=True, text=True)
    assert missing.returncode != 0
    assert 'nao encontrado' in missing.stdout + missing.stderr
    assert not output.exists()
    raw.write_bytes(b'')
    empty = subprocess.run(command, capture_output=True)
    assert empty.returncode == 0
    assert output.read_bytes().count(b'\n') == 1
