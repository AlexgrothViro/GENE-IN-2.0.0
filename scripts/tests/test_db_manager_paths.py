"""Real index metadata regression; no searches, read mapping or assembly."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evidence"))
import index_cache
from verify_blast_database_manifest import verify


class SharedIndexCacheTests(unittest.TestCase):
    def test_changed_reference_rejects_shared_receipt_with_extra_builders(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.fa"
            reference.write_text(">fixture\nACGT\n")
            timestamp = reference.stat().st_mtime_ns
            with patch.object(index_cache, "builder_identity", side_effect=lambda name: {"command": name, "version": "unchanged"}):
                receipt = index_cache.fingerprint(reference, ["makeblastdb", "bowtie2-build"])
                self.assertTrue(index_cache.matches(receipt, reference, ["makeblastdb"]))
                reference.write_text(">fixture\nTGCA\n")
                os.utime(reference, ns=(timestamp, timestamp))
                self.assertFalse(index_cache.matches(receipt, reference, ["makeblastdb"]))

    def test_required_builder_subset_reuses_shared_receipt_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.fa"
            reference.write_text(">fixture\nACGT\n")
            identities = {name: {"version": "fixture", "sha256": name} for name in ("makeblastdb", "bowtie2-build")}
            with patch.object(index_cache, "builder_identity", side_effect=lambda name: identities[name].copy()):
                receipt = index_cache.fingerprint(reference, list(identities))
                self.assertTrue(index_cache.matches(receipt, reference, ["makeblastdb"]))
                self.assertTrue(index_cache.matches(receipt, reference, list(identities)))
                identities["bowtie2-build"]["version"] = "changed"
                self.assertTrue(index_cache.matches(receipt, reference, ["makeblastdb"]))
                self.assertFalse(index_cache.matches(receipt, reference, list(identities)))
                identities["makeblastdb"]["version"] = "changed"
                self.assertFalse(index_cache.matches(receipt, reference, ["makeblastdb"]))
                reference.write_text(">fixture\nTGCA\n")
                self.assertFalse(index_cache.matches(receipt, reference, ["makeblastdb"]))


TOOLS = ("makeblastdb", "blastdbcmd", "blastdb_aliastool", "bowtie2-build", "bowtie2-inspect")


@unittest.skipUnless(os.name == "posix" and all(shutil.which(tool) for tool in TOOLS), "real index tools on POSIX are required")
class RealIndexPathTests(unittest.TestCase):
    def test_spaced_directory_and_basename_prepare_verify_reuse_and_preserve_generation(self):
        for basename in ("fixture", "fixture with spaces"):
            with self.subTest(basename=basename), tempfile.TemporaryDirectory(prefix="genein index files ") as directory:
                work = Path(directory)
                reference = work / "reference file.fa"
                reference.write_text(">fixture_a\nACGT\n>fixture_b\nTGCA\n")
                prefix = work / basename
                env = {**os.environ, "DB": "fixture", "REF_FASTA": str(reference), "BLAST_DB": str(prefix),
                       "BOWTIE2_INDEX": str(work / "mapping index"), "GENEIN_WORK_ROOT": str(work),
                       "GENEIN_CONFIG_FILE": str(work / "absent config")}

                def prepare(environment, mode="setup"):
                    return subprocess.run(["bash", str(ROOT / "scripts/ops/db_manager.sh"), mode],
                                          cwd=work, env=environment, capture_output=True, text=True, timeout=60)

                first = prepare(env)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                manifest_path = Path(str(prefix) + ".db-manifest.json")
                original_manifest = manifest_path.read_bytes()
                original_alias = Path(str(prefix) + ".nal").read_bytes()
                self.assertGreater(verify(prefix), 0)
                second = prepare(env)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertIn("BLAST DB atualizado", second.stdout)
                self.assertIn("Índice Bowtie2 atualizado", second.stdout)
                self.assertEqual(manifest_path.read_bytes(), original_manifest)

                manifest = json.loads(original_manifest)
                generation = work / ("." + hashlib.sha256(basename.encode()).hexdigest() + ".generations") / manifest["generation_id"]
                component = generation / next(iter(manifest["produced_files"]))
                original_component = component.read_bytes()
                try:
                    component.write_bytes(original_component + b"changed")
                    with self.assertRaisesRegex(ValueError, "alterado ou incompleto"):
                        verify(prefix)
                finally:
                    component.write_bytes(original_component)
                try:
                    manifest_path.write_text(json.dumps({**manifest, "index_basename": "../database"}))
                    with self.assertRaisesRegex(ValueError, "inválido"):
                        verify(prefix)
                finally:
                    manifest_path.write_bytes(original_manifest)

                fake_bin = work / "controlled tools"
                fake_bin.mkdir()
                fake = fake_bin / "makeblastdb"
                fake.write_text('#!/bin/sh\nif [ "$1" = "-version" ]; then echo controlled-failure; exit 0; fi\nexit 19\n')
                fake.chmod(0o755)
                failed = prepare({**env, "PATH": str(fake_bin) + os.pathsep + env["PATH"]}, "setup-blast")
                self.assertEqual(failed.returncode, 19, failed.stdout + failed.stderr)
                self.assertEqual(manifest_path.read_bytes(), original_manifest)
                self.assertEqual(Path(str(prefix) + ".nal").read_bytes(), original_alias)
                self.assertGreater(verify(prefix), 0)


if __name__ == "__main__":
    unittest.main()
