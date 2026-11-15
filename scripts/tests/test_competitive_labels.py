"""Identifier metadata preflight only; no search or alignment."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evidence"))
from aggregate_hsps import load_labels
from check_competitive_labels import check_subject_labels


class CompetitiveLabelTests(unittest.TestCase):
    def check(self, identifiers, labels):
        with patch("check_competitive_labels.subprocess.run", return_value=SimpleNamespace(stdout="\n".join(identifiers))) as tool:
            result = check_subject_labels(Path("/files with spaces/bank with spaces"), labels)
            self.assertEqual(tool.call_args.args[0][2], '"/files with spaces/bank with spaces"')
            return result

    def test_equal_identifier_sets_pass(self):
        result = self.check(["id-a", "id-b"], {"id-a": {}, "id-b": {}})
        self.assertEqual(result["database_id_count"], 2)
        self.assertEqual(result["label_count"], 2)

    def test_database_id_without_label_is_listed(self):
        with self.assertRaisesRegex(ValueError, r"IDs do banco sem rótulo: total=1, exemplos=\['id-b'\]"):
            self.check(["id-a", "id-b"], {"id-a": {}})

    def test_orphan_label_is_listed(self):
        with self.assertRaisesRegex(ValueError, r"rótulos sem ID no banco: total=1, exemplos=\['orphan'\]"):
            self.check(["id-a"], {"id-a": {}, "orphan": {}})

    def test_duplicate_label_is_rejected_before_database_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.tsv"
            path.write_text("sseqid\tcategory\nid-a\tTARGET_VIRUS\nid-a\tHOST\n")
            with self.assertRaisesRegex(ValueError, "[Dd]uplicate"):
                load_labels(str(path))

    def test_message_limits_examples_to_twenty_and_reports_total(self):
        ids = [f"id-{i:02d}" for i in range(25)]
        with self.assertRaises(ValueError) as error:
            self.check(ids, {})
        self.assertIn("total=25", str(error.exception))
        self.assertIn("id-19", str(error.exception))
        self.assertNotIn("id-20", str(error.exception))

    def test_inspector_failure_is_a_preflight_error(self):
        with patch("check_competitive_labels.subprocess.run", side_effect=FileNotFoundError("controlled")):
            with self.assertRaisesRegex(ValueError, "Não foi possível listar"):
                check_subject_labels(Path("bank"), {})


@unittest.skipUnless(shutil.which("makeblastdb") and shutil.which("blastdbcmd"), "PULOU: makeblastdb/blastdbcmd ausentes")
class RealIdentifierMetadataTests(unittest.TestCase):
    def test_accessions_from_real_index_match_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "bank"
            built = subprocess.run(["makeblastdb", "-in", "-", "-title", "identifier metadata fixture", "-dbtype", "nucl", "-parse_seqids", "-out", str(prefix)], input=">id-a\nACGT\n>id-b\nTGCA\n", capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            self.assertEqual(check_subject_labels(prefix, {"id-a": {}, "id-b": {}})["database_id_count"], 2)


if __name__ == "__main__":
    unittest.main()
