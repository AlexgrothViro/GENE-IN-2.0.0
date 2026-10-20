from unittest.mock import patch
import shutil
import pytest
from scripts.dashboard import jobs, handler


@pytest.mark.parametrize('suffix', ['.fastq.gz', '.fastq'])
def test_listed_pair_is_used_without_rewriting(tmp_path, suffix):
    shutil.copytree(jobs.REPO_ROOT/'config', tmp_path/'config')
    raw = tmp_path/'data/raw'
    raw.mkdir(parents=True)
    files = [raw/f'TEST_R{mate}{suffix}' for mate in (1, 2)]
    for path in files:
        path.write_bytes(b'unchanged input bytes')
    with patch.object(handler, 'REPO_ROOT', tmp_path), patch.object(jobs, 'REPO_ROOT', tmp_path):
        assert 'TEST' in handler.list_samples()
        cmd, _ = jobs.build_command('evidence_pipeline', dict(sample='TEST', db='ptv', host_filter_mode='none'))
    assert cmd[cmd.index('--r1') + 1] == str(files[0])
    assert cmd[cmd.index('--r2') + 1] == str(files[1])
    assert all(path.read_bytes() == b'unchanged input bytes' for path in files)
