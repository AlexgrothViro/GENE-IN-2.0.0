"""Distribution checks: source allowlist, permissions, hashes and provenance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

from scripts.ops.build_release import build_release
from scripts.lib.validation import runtime
from unittest.mock import patch


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'source with spaces'
        self.root.mkdir()
        self.git('init', '-q')
        (self.root / 'pyproject.toml').write_text('[project]\nversion="2.0.0rc1"\n')
        (self.root / 'RELEASE.json').write_text(json.dumps({'software_version': '2.0.0rc1'}))
        (self.root / 'nested').mkdir()
        (self.root / 'nested/run.sh').write_text('#!/bin/bash\necho hello\n')
        (self.root / 'fixture.fa').write_text('>known\nACGT\n')
        (self.root / '.gitignore').write_text('*.fa\nconfig.env\n__pycache__/\n')
        self.git('add', '.')
        self.git('add', '-f', 'fixture.fa')
        self.git('-c', 'user.name=Release Test', '-c', 'user.email=release@example.invalid', 'commit', '-qm', 'fixture')
        (self.root / 'config.env').write_text('PRIVATE_CONFIG=value\n')
        (self.root / 'untracked.txt').write_text('not approved for release\n')
        (self.root / '__pycache__').mkdir()
        (self.root / '__pycache__/module.pyc').write_bytes(b'cache')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL)

    def test_archives_only_contain_tracked_source_with_hashes_and_shell_modes(self):
        out = Path(self.tmp.name) / 'delivery'
        record = build_release(self.root, out)
        self.assertEqual(record['source_commit'], self.git('rev-parse', 'HEAD').decode().strip())
        with zipfile.ZipFile(out / record['source_archive_name']) as archive:
            names = archive.namelist()
            self.assertIn('Gene-In-2.0.0rc1/fixture.fa', names)
            self.assertFalse(any(s in n for n in names for s in ('config.env', 'untracked', '__pycache__', '.git/')))
            self.assertEqual(archive.getinfo('Gene-In-2.0.0rc1/nested/run.sh').external_attr >> 16 & 0o777, 0o755)
            manifest = archive.read('Gene-In-2.0.0rc1/SOURCE_MANIFEST.sha256').decode()
            for line in manifest.splitlines():
                digest, rel = line.split('  ', 1)
                self.assertEqual(hashlib.sha256(archive.read('Gene-In-2.0.0rc1/' + rel)).hexdigest(), digest)
        with tarfile.open(out / 'Gene-In-2.0.0rc1.tar.gz') as archive:
            self.assertEqual(archive.getmember('Gene-In-2.0.0rc1/nested/run.sh').mode, 0o755)
        other = Path(self.tmp.name) / 'repeat'
        self.assertEqual(build_release(self.root, other)['archives'], record['archives'])
        with self.assertRaises(FileExistsError):
            build_release(self.root, out)

    def test_dirty_checkout_rejected(self):
        (self.root / 'nested/run.sh').write_text('uncommitted change\n')
        with self.assertRaisesRegex(ValueError, 'commit tracked'):
            build_release(self.root, Path(self.tmp.name) / 'dirty')

    def test_unsafe_name_rejected_before_output(self):
        out = Path(self.tmp.name) / 'unsafe'
        for name in ('../outside', '/absolute', 'has spaces'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_release(self.root, out, name)
        self.assertFalse(out.exists())


class TrackEnvironmentTests(unittest.TestCase):
    def test_explicit_prefix_is_used_without_falling_back(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            home = Path(tmp)
            default = home / '.gene-in-bundle/env/bin'
            selected = home / 'selected/env/bin'
            for directory in (default, selected):
                directory.mkdir(parents=True)
                (directory / 'blastn').touch()
            os.environ['GENEIN_BUNDLE_DIR'] = str(home / 'selected')
            self.assertEqual(runtime.genein_bundle_env_bin(home), selected)
            os.environ['GENEIN_ENV_DIR'] = str(home / 'missing')
            with self.assertRaises(FileNotFoundError):
                runtime.ensure_genein_bundle_path(home)

    def test_existing_selected_path_preserves_active_test_python(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            selected = Path(tmp) / 'selected/bin'
            selected.mkdir(parents=True)
            (selected / 'blastn').touch()
            os.environ['GENEIN_ENV_DIR'] = str(selected.parent)
            os.environ['PATH'] = os.pathsep.join(('/test-venv/bin', str(selected), '/usr/bin'))
            before = os.environ['PATH']
            runtime.ensure_genein_bundle_path()
            self.assertEqual(os.environ['PATH'], before)


if __name__ == '__main__':
    unittest.main()
