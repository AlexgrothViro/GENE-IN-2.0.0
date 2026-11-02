import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/evidence"))

if os.name == "nt":
    raise unittest.SkipTest("file locking test requires a POSIX host")

import promote_blast_database
from verify_blast_database_manifest import verify


class BlastDatabasePromotionTests(unittest.TestCase):
    def make_build(self, root: Path, name: str, marker: str) -> Path:
        build = root / f".{name}.build-{marker}"
        build.mkdir()
        for extension in ("ndb", "nhr", "nin", "njs", "not", "nsq", "ntf", "nto"):
            (build / f"{name}.{extension}").write_text(f"{marker}-{extension}\n", encoding="utf-8")
        return build

    @staticmethod
    def fake_tools(command: list[str], description: str, *, cwd: Path | None = None) -> None:
        if "-out" in command:
            output = Path(command[command.index("-out") + 1])
            assert cwd is not None and not output.is_absolute()
            generation = command[command.index("-dblist") + 1].strip('"')
            assert not Path(generation).is_absolute()
            assert (cwd / generation).parent.is_dir()
            output = cwd / output
            Path(f"{output}.nal").write_text("DBLIST fake-generation\n", encoding="utf-8")

    def test_two_rebuilds_replace_the_complete_generation_without_mixing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.fa"
            reference.write_text(">ref\nACGT\n", encoding="utf-8")
            destination = root / "ptv"
            manifest = root / "ptv.db-manifest.json"
            (root / "ptv.old-extension").write_text("legacy\n", encoding="utf-8")
            with patch.object(promote_blast_database, "run_checked", side_effect=self.fake_tools):
                promote_blast_database.promote(
                    self.make_build(root, "ptv", "one"), destination, reference,
                    "blastdbcmd", "blastdb_aliastool", manifest,
                )
                first_generation = next((root / ".ptv.generations").iterdir())
                promote_blast_database.promote(
                    self.make_build(root, "ptv", "two"), destination, reference,
                    "blastdbcmd", "blastdb_aliastool", manifest,
                )
            generations = list((root / ".ptv.generations").iterdir())
            self.assertEqual(len(generations), 1)
            self.assertNotEqual(generations[0], first_generation)
            self.assertFalse((root / "ptv.old-extension").exists())
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(len(data["produced_files"]), 8)
            self.assertEqual(len(data["source_fasta"]["sha256"]), 64)
            for details in data["produced_files"].values():
                self.assertEqual(len(details["sha256"]), 64)

    def test_failure_after_alias_swap_restores_previous_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.fa"
            reference.write_text(">ref\nACGT\n", encoding="utf-8")
            destination = root / "ptv"
            final_alias = root / "ptv.nal"
            final_alias.write_bytes(b"DBLIST old-generation\n")
            old_generation = root / ".ptv.generations/old-generation"
            old_generation.mkdir(parents=True)
            manifest = root / "ptv.db-manifest.json"

            def fail_promoted_validation(command: list[str], description: str, *, cwd: Path | None = None) -> None:
                self.fake_tools(command, description, cwd=cwd)
                if description == "promoted BLAST database validation":
                    raise RuntimeError("simulated validation failure")

            with patch.object(promote_blast_database, "run_checked", side_effect=fail_promoted_validation):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    promote_blast_database.promote(
                        self.make_build(root, "ptv", "new"), destination, reference,
                        "blastdbcmd", "blastdb_aliastool", manifest,
                    )
            self.assertEqual(final_alias.read_bytes(), b"DBLIST old-generation\n")
            self.assertTrue(old_generation.is_dir())
            self.assertFalse(manifest.exists())

    def test_physical_basename_manifest_and_legacy_storage_both_verify(self):
        for build_name in (None, "database"):
            with self.subTest(build_name=build_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                destination = root / "logical with spaces"
                reference = root / "reference.fa"
                reference.write_text(">fixture\nACGT\n")
                manifest_path = Path(str(destination) + ".db-manifest.json")

                def tools(command, description, *, cwd=None):
                    self.fake_tools(command, description, cwd=cwd)
                    if "-out" in command:
                        alias = cwd / (command[command.index("-out") + 1] + ".nal")
                        alias.write_text("DBLIST " + json.dumps(command[command.index("-dblist") + 1].strip('"')) + "\n")

                with patch.object(promote_blast_database, "run_checked", side_effect=tools):
                    promote_blast_database.promote(
                        self.make_build(root, build_name or destination.name, "new"), destination,
                        reference, "blastdbcmd", "blastdb_aliastool", manifest_path,
                        build_name=build_name,
                    )
                self.assertEqual(verify(destination), 8)
                manifest = json.loads(manifest_path.read_text())
                if build_name is not None:
                    manifest["index_basename"] = "../escape"
                    manifest_path.write_text(json.dumps(manifest))
                    with self.assertRaisesRegex(ValueError, "inválido"):
                        verify(destination)


if __name__ == "__main__":
    unittest.main()
