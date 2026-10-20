import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts.evidence.write_provenance import version

ROOT = Path(__file__).resolve().parents[2]


class ProvenanceVersionTests(unittest.TestCase):
    def test_index_cache_does_not_record_usage_error(self):
        from scripts.evidence.index_cache import builder_identity
        with patch("scripts.evidence.index_cache.shutil.which", return_value="/bin/makeblastdb"), patch(
            "scripts.evidence.index_cache.sha256_file", return_value="a" * 64
        ), patch("scripts.evidence.index_cache.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 1, "USAGE\n", ""),
            subprocess.CompletedProcess([], 0, "makeblastdb: 2.17.0+\n", "")
        ]):
            self.assertEqual(builder_identity("makeblastdb")["version"], "makeblastdb: 2.17.0+")

    def test_fastq_errors_identify_header_separator_and_quality(self):
        from scripts.lib.input_validation import validate_fastq
        cases = [("invalid\nAC\n+\nII\n", "cabeçalho"),
                 ("@read\nAC\nwrong\nII\n", "terceira linha"),
                 ("@read\nAC\n+\nI\n", "tamanhos diferentes")]
        with tempfile.TemporaryDirectory() as tmp:
            fastq = Path(tmp) / "bad.fastq"
            for data, reason in cases:
                with self.subTest(reason=reason):
                    fastq.write_text(data)
                    with self.assertRaisesRegex(ValueError, reason):
                        validate_fastq(fastq)

    def test_dashboard_accepts_iqtree_command_alias(self):
        from scripts.dashboard import config
        def resolve(name, **kwargs):
            return None if name in {"iqtree2", "iqtree3"} else f"/chosen/env/bin/{name}"
        with patch.object(config, "runtime_environment", return_value={"PATH": "/chosen/env/bin"}), patch.object(config.shutil, "which", side_effect=resolve):
            report = config.get_preflight_status()
        iqtree = next(tool for tool in report["tools"] if tool["name"] == "iqtree2")
        self.assertTrue(iqtree["present"])
        self.assertEqual(iqtree["path"], "/chosen/env/bin/iqtree")

    def test_blast_version_uses_supported_flag(self):
        with patch("scripts.evidence.write_provenance.shutil.which", return_value="/bin/blastn"), patch(
            "scripts.evidence.write_provenance.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "blastn: 2.17.0+\n", ""),
        ) as run:
            self.assertEqual(version("blastn"), "blastn: 2.17.0+")
            self.assertEqual(run.call_args.args[0], ["blastn", "-version"])

    def test_usage_error_is_not_recorded_as_version(self):
        with patch("scripts.evidence.write_provenance.shutil.which", return_value="/bin/tool"), patch(
            "scripts.evidence.write_provenance.subprocess.run",
            side_effect=[subprocess.CompletedProcess([], 1, "", "USAGE\n"),
                         subprocess.CompletedProcess([], 0, "tool: 1.2\n", "")],
        ):
            self.assertEqual(version("tool"), "tool: 1.2")

    def test_zero_exit_usage_text_is_not_a_version(self):
        from scripts.evidence.index_cache import builder_identity
        for module, call in (("scripts.evidence.index_cache", lambda: builder_identity("tool")["version"]),
                             ("scripts.evidence.write_provenance", lambda: version("tool"))):
            with self.subTest(module=module), patch(module + ".shutil.which", return_value="/bin/tool"), patch(
                module + ".subprocess.run", side_effect=[
                    subprocess.CompletedProcess([], 0, "USAGE\n", ""),
                    subprocess.CompletedProcess([], 0, "tool: 1.2\n", "")
                ]), patch("scripts.evidence.index_cache.sha256_file", return_value="a" * 64):
                self.assertEqual(call(), "tool: 1.2")


@unittest.skipUnless(os.name == "posix", "Linux installer")
class InstallerSystemRequirementsTests(unittest.TestCase):
    def test_missing_make_is_reported_before_environment_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            for name in ("dirname", "python3", "curl", "tar", "bzip2", "install", "find", "chmod"):
                import shutil
                path = shutil.which(name)
                if path:
                    (bin_dir / name).symlink_to(path)
            (bin_dir / "uname").write_text('#!/bin/sh\ncase "$1" in -s) echo Linux;; -m) echo x86_64;; esac\n')
            (bin_dir / "apt-get").write_text('#!/bin/sh\necho "APT_ATTEMPT:$*" >&2\nexit 42\n')
            (bin_dir / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
            for name in ("uname", "apt-get", "sudo"):
                (bin_dir / name).chmod(0o755)
            env = dict(os.environ, PATH=tmp, GENEIN_BUNDLE_DIR=tmp + "/bundle")
            result = subprocess.run(["/bin/bash", str(ROOT / "bundle/install_wsl.sh")], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
            self.assertIn("ausentes: make", result.stderr)
            self.assertIn("APT_ATTEMPT:update", result.stderr)
            self.assertFalse((bin_dir / "bundle").exists())
