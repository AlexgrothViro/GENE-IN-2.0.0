import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != 'posix', reason='Sinais POSIX')
@pytest.mark.parametrize('failure', ['signal', 'exit'])
def test_router_removes_temp_on_failure(tmp_path, failure):
    root = Path(__file__).resolve().parents[2]
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in {
        'blastdbcmd': '#!/bin/sh\necho "2 sequences;"\n',
        'blastn': '#!/bin/sh\n' + ('sleep 30\n' if failure == 'signal' else 'exit 42\n'),
    }.items():
        path = bin_dir / name
        path.write_text(body)
        path.chmod(0o755)
    query = tmp_path / 'queries.fa'
    query.write_text('>q\nACGTACGTACGTACGTACGT\n')
    env = dict(os.environ, TMPDIR=str(tmp_path), PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
    process = subprocess.Popen([sys.executable, str(root/'scripts/evidence/blast_router.py'), '--query', str(query), '--db', str(tmp_path/'db'), '--out-combined', str(tmp_path/'out.tsv')], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        if failure == 'signal':
            deadline = time.monotonic() + 10
            while not list(tmp_path.glob('genein-blast-router-*/short.fa')) and time.monotonic() < deadline:
                time.sleep(0.05)
            assert list(tmp_path.glob('genein-blast-router-*'))
            os.killpg(process.pid, signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode != 0, (stdout, stderr)
        assert not list(tmp_path.glob('genein-blast-router-*'))
        assert not (tmp_path/'out.tsv').exists()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
