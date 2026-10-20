import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_installer_checks_make_before_creating_environment(tmp_path):
    for name in ('dirname', 'python3', 'curl', 'tar', 'bzip2', 'install', 'find', 'chmod'):
        (tmp_path / name).symlink_to(shutil.which(name))
    for name, data in {
        'uname': '#!/bin/sh\ncase "$1" in -s) echo Linux;; -m) echo x86_64;; esac\n',
        'apt-get': '#!/bin/sh\necho "APT_ATTEMPT:$*" >&2\nexit 42\n',
        'sudo': '#!/bin/sh\nexec "$@"\n',
    }.items():
        (tmp_path / name).write_text(data)
        (tmp_path / name).chmod(0o755)
    result = subprocess.run(['/bin/bash', str(ROOT / 'bundle/install_wsl.sh')], env=dict(os.environ, PATH=str(tmp_path), GENEIN_BUNDLE_DIR=str(tmp_path / 'bundle')), capture_output=True)
    assert result.returncode == 42
    assert b'ausentes: make' in result.stderr
    assert not (tmp_path / 'bundle').exists()


def test_environment_install_commands_unchanged_byte_for_byte():
    old = (ROOT / 'scripts/tests/fixtures/b1_reference/install_wsl.sh.txt').read_bytes()
    new = (ROOT / 'bundle/install_wsl.sh').read_bytes()
    marker = '# Instala micromamba'.encode()
    assert old[old.index(marker):] == new[new.index(marker):]
