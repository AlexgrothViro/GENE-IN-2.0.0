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
    assert result.returncode == 2
    assert b'ausentes: make' in result.stderr
    assert b'Missing system prerequisites: make' in result.stderr
    assert b'Instala\xc3\xa7\xc3\xa3o interrompida; o apt-get falhou.' in result.stderr
    assert b'Installation stopped; apt-get failed.' in result.stderr
    assert b'Instale make e rode de novo: bash bundle/install_wsl.sh' in result.stderr
    assert b'APT_ATTEMPT:update' in result.stderr
    assert result.stderr.count(b'APT_ATTEMPT:') == 1
    assert b'[OK]' not in result.stdout + result.stderr
    assert not (tmp_path / 'bundle').exists()


def test_environment_install_commands_unchanged_byte_for_byte():
    old = (ROOT / 'scripts/tests/fixtures/b1_reference/install_wsl.sh.txt').read_bytes()
    new = (ROOT / 'bundle/install_wsl.sh').read_bytes()
    # The micromamba download is pinned separately. This lock covers the
    # recorded environment install that follows that download.
    marker = b'# Install exact recorded dependencies'
    assert old[old.index(marker):] == new[new.index(marker):]
