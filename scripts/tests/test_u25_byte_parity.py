from pathlib import Path
import subprocess
from unittest.mock import patch
import scripts.dashboard.config as config


def test_index_requires_all_components_and_inspection(tmp_path):
    prefix = tmp_path / 'host'
    (tmp_path / 'host.fa').write_text('>host\nACGT\n')
    assert not config.validate_host_index(str(prefix))['valid']
    for part in ('1', '2', '3', '4', 'rev.1', 'rev.2'):
        Path(f'{prefix}.{part}.bt2').write_bytes(b'component')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with patch.object(config, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
        assert config.validate_host_index(str(prefix))['valid']
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    with patch.object(config, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')):
        assert not config.validate_host_index(str(prefix))['valid']


def test_host_preflight_precedes_qc():
    source = (Path(__file__).resolve().parents[2] / 'scripts/pipeline/sample_steps.sh').read_text()
    assert source.index('validate_bt2_index "$HOST_INDEX_PREFIX"') < source.index('"$SCRIPT_DIR/qc_fastp.sh"')
