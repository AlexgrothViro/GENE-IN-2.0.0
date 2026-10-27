import os
import shutil
import subprocess
from pathlib import Path
import pytest


@pytest.mark.skipif(os.name != 'posix', reason='Wrapper Linux')
@pytest.mark.parametrize('wrapper', ['bundle/run.sh', 'run_linux.sh'])
def test_wrapper_without_make_is_actionable(tmp_path, wrapper):
    root = Path(__file__).resolve().parents[2]
    for tool in ('bash', 'dirname', 'uname'):
        (tmp_path/tool).symlink_to(shutil.which(tool))
    result = subprocess.run([shutil.which('bash'), str(root/wrapper), 'test-env'], env=dict(os.environ, PATH=str(tmp_path)), capture_output=True, text=True)
    assert result.returncode == 2
    assert 'make não encontrado' in result.stderr
    assert 'bash bundle/install_wsl.sh' in result.stderr
    assert 'exec: make' not in result.stderr


def test_wrapper_forwards_interrupt_to_the_child_tree():
    text = (Path(__file__).resolve().parents[2] / "bundle/run.sh").read_text(encoding="utf-8")
    assert "genein_run_tree" in text
    assert "CANCELADO" in text
    assert "setsid" in text
    assert 'exec "$MICRO" run -p "$ENV_DIR" python -m genein' not in text
    assert 'exec "$MICRO" run -p "$ENV_DIR" make' not in text
