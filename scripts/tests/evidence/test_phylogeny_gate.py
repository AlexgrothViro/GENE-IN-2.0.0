import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from phylogeny_gate import evaluate


CONFIG = {"phylogeny": {"minimum_aligned_bp": 200, "minimum_informative_sites": 20, "minimum_references": 4, "maximum_n_fraction": 0.05, "maximum_gap_fraction": 0.50}}


class PhylogenyGateTests(unittest.TestCase):
    def fixture(self, root: Path):
        base = list(("ACGT" * 55)[:220])
        names = ["query", "ref1", "ref2", "ref3", "ref4", "ref5"]
        sequences = {}
        for index, name in enumerate(names):
            sequence = base.copy()
            for position in range(0, 80, 4):
                sequence[position] = "A" if index < 3 else "C"
            sequences[name] = "".join(sequence)
        alignment = root / "alignment.fa"
        alignment.write_text("".join(f">{name}\n{seq}\n" for name, seq in sequences.items()), encoding="utf-8")
        query = root / "query.fa"; query.write_text(f">query\n{sequences['query']}\n", encoding="utf-8")
        refs = root / "refs.fa"; refs.write_text("".join(f">{name}\n{sequences[name]}\n" for name in names[1:]), encoding="utf-8")
        metadata = root / "metadata.tsv"
        metadata.write_text("sseqid\ttaxon_group\tis_outgroup\nref1\tA\tfalse\nref2\tA\tfalse\nref3\tB\tfalse\nref4\tB\tfalse\nref5\tOUT\ttrue\n", encoding="utf-8")
        return alignment, query, refs, metadata

    def test_balanced_panel_can_pass_operational_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            alignment, query, refs, metadata = self.fixture(Path(tmp))
            result = evaluate(str(alignment), str(query), str(refs), CONFIG, str(metadata), iqtree_available=True)
            self.assertEqual(result["gate_status"], "PASS")

    def test_missing_metadata_and_iqtree_block_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            alignment, query, refs, _ = self.fixture(Path(tmp))
            result = evaluate(str(alignment), str(query), str(refs), CONFIG, iqtree_available=False)
            self.assertEqual(result["gate_status"], "BLOCKED")
            self.assertIn("REFERENCE_PANEL_METADATA_MISSING", result["flags"])
            self.assertIn("IQTREE_UNAVAILABLE", result["flags"])


if __name__ == "__main__":
    unittest.main()
