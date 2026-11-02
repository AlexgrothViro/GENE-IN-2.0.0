"""Guard against silent skips and a zero exit without committed outputs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.tests import run_optional_e2e as runner


class OptionalE2EContractTests(unittest.TestCase):
    def test_missing_tools_emit_skip_manifest_and_exit_77(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner.shutil, "which", return_value=None):
                code = runner.main(["--artifact-root", directory])
            self.assertEqual(code, 77)
            manifest = json.loads(next(Path(directory).rglob("e2e-manifest.json")).read_text())
            self.assertEqual(manifest["status"], "SKIPPED")
            self.assertIn("blastn", manifest["missing_tools"])
            self.assertIn("bowtie2", manifest["missing_tools"])
            self.assertEqual(manifest["cases"], [])
            self.assertEqual(manifest["commands"], [])

    def test_zero_exit_cannot_replace_a_missing_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                runner.check_run(Path(directory), "current-run", True, True, {})

    def test_fixture_is_repeatable_and_contains_only_requested_lengths(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            fixture = runner.fixtures(Path(first))
            repeated = runner.fixtures(Path(second))
            for name in ("primary", "panel", "labels", "r1", "r2"):
                self.assertEqual(fixture[name].read_bytes(), repeated[name].read_bytes())
            records = fixture["r1"].read_text().splitlines()
            lengths = {len(records[index]) for index in range(1, len(records), 4)}
            self.assertEqual(lengths, set(runner.LENGTHS))
            self.assertEqual(min(lengths), 20)
            self.assertEqual(max(lengths), 100)
            self.assertTrue(all(set(records[index]) <= set("ACGT") for index in range(1, len(records), 4)))


if __name__ == "__main__":
    unittest.main()
