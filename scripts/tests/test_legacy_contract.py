import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "scripts" / "legacy"


class LegacyContractTests(unittest.TestCase):
    def test_advanced_runner_is_repo_relative_and_does_not_call_shared_make_test(self):
        text = (LEGACY / "run_ptv_advanced.sh").read_text(encoding="utf-8")
        self.assertNotIn('ROOT_DIR="$(pwd)"', text)
        self.assertNotIn("make test SAMPLE", text)
        self.assertIn('LEGACY_WORK_DIR', text)
        self.assertIn('LEGACY_BLAST_DB', text)
        self.assertIn('scripts/pipeline/adj_identity.py', text)
        self.assertIn('scripts/pipeline/label_hits.py', text)
        self.assertNotIn('${ROOT_DIR}/scripts/adj_identity.py', text)
        self.assertNotIn('${ROOT_DIR}/scripts/label_hits.py', text)

    def test_legacy_python_defaults_use_isolated_work_contract(self):
        for name in ("sim_reads_clean.py", "merge_report.py", "emit_extend_fasta.py", "collect_ptv_contigs.py"):
            text = (LEGACY / name).read_text(encoding="utf-8")
            self.assertIn("WORK_DIR", text, name)

    def test_region_fasta_rejects_invalid_coordinates_without_external_tools(self):
        result = subprocess.run(
            [sys.executable, str(LEGACY / "build_ptv_region_fasta.py"),
             "report.tsv", "fragments.fa", "reference.fa", "out.fa", "ref", "0", "10"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("coorden", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
