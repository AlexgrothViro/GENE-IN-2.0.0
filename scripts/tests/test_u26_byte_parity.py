import importlib.util
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('u26_config', ROOT / 'scripts/dashboard/config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def effective(path):
    return subprocess.check_output(['bash', '-c', 'source "$1"; printf "%s\\0%s" "$SPADES_MEMORY" "$SPADES_PARAMS"', 'test', str(path)])


def test_save_preserves_effective_spades_parameters_byte_for_byte():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'config.env'
        path.write_text('SPADES_MEMORY=12\nSPADES_PARAMS="-m ${SPADES_MEMORY}"\nTHREADS=4\n')
        before = effective(path)
        with patch.object(config, 'CONFIG_ENV_PRIMARY', path):
            config.save_config_env(config.load_config_env())
        assert effective(path) == before
        with patch.object(config, 'CONFIG_ENV_PRIMARY', path):
            config.save_config_env({'SPADES_MEMORY': '16'})
        assert effective(path) == b'16\0-m 16'


def test_only_documented_memory_reference_expands():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'config.env'
        marker = Path(tmp) / 'executed'
        value = f'-m ${{SPADES_MEMORY}} $(touch {marker}) `touch {marker}` $HOME "quoted" \\literal'
        path.write_text('SPADES_MEMORY=12\n')
        with patch.object(config, 'CONFIG_ENV_PRIMARY', path):
            config.save_config_env({'SPADES_PARAMS': value})
        assert effective(path) == ('12\0' + value.replace('${SPADES_MEMORY}', '12')).encode()
        assert not marker.exists()
