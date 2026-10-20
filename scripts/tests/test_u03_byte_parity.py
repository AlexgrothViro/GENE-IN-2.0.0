from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_known_context_logs_match_b1_bytes():
    def log(path, context):
        return subprocess.check_output(['bash', '-c', 'source "$1"; ' + context + '; log_info "message"', 'test', str(path)])
    old = ROOT / 'scripts/tests/fixtures/b1_reference/common.sh.txt'
    new = ROOT / 'scripts/lib/common.sh'
    context = 'PIPELINE_ETAPA=ASSEMBLY; SAMPLE_NAME=SAMPLE'
    assert log(old, context) == log(new, context)
    assert b'[?]' not in log(new, 'unset PIPELINE_ETAPA SAMPLE_NAME')
