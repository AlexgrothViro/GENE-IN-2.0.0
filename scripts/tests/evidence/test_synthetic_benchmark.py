import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "benchmark"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from blast_router import profiles_for_length
from classify_sample import classify
from activation_policy import load_public_activation_policy
from generate_synthetic_matrix import LENGTHS, generate


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_matrix_has_required_boundaries_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            first, second = Path(left), Path(right)
            summary = generate(first); generate(second)
            self.assertEqual(summary["sequences"], 60)
            self.assertEqual((first / "short_fragment_matrix.fasta").read_bytes(), (second / "short_fragment_matrix.fasta").read_bytes())
            table = (first / "short_fragment_matrix.tsv").read_text(encoding="utf-8")
            for length in (20, 29, 30, 49, 50, 79, 80, 99, 100, 200):
                self.assertIn(f"_{length}bp", table)
            self.assertIn("\tdual\tEXPLORATORY_FRAGMENT", table)

    def test_every_length_from_20_to_100_preserves_routing_and_open_results(self):
        config = load_public_activation_policy()["thresholds"]
        for length in range(20, 101):
            with self.subTest(length=length):
                profiles = profiles_for_length(length, config)
                expected_profiles = (
                    ("short",) if length < 30
                    else (("short", "conventional") if length < 50 else ("conventional",))
                )
                self.assertEqual(profiles, expected_profiles)
                locus = {
                    "locus_id": f"L{length}",
                    "sseqid": "synthetic-virus",
                    "query_ids": f"q{length}",
                    "orientation": "+",
                    "task": "blastn-short" if length < 50 else "blastn",
                    "category": "TARGET_VIRUS",
                    "covered_reference_bp": str(length),
                    "max_query_length": str(length),
                }
                competitive = {
                    "qseqid": f"q{length}",
                    "task": locus["task"],
                    "specificity_status": "TARGET_SPECIFIC",
                }
                result = classify(
                    f"synthetic-{length}",
                    [locus],
                    [competitive],
                    [],
                    [],
                    "UNCONTROLLED",
                    "shotgun",
                    False,
                )
                candidate = result["candidates"][0]
                self.assertEqual(result["evidence_level"], "DETECTED")
                self.assertEqual(result["reported_conclusion"], "EVIDENCE_RECOVERED")
                self.assertEqual(
                    candidate["candidate_class"],
                    "EXPLORATORY_FRAGMENT" if length < 50 else "LOCUS_CANDIDATE",
                )
                self.assertEqual(candidate["promotion_status"], "AVAILABLE")
                self.assertEqual(candidate["blocking_reasons"], [])
                self.assertEqual(result["promotion_gates"], [])

    def test_boundary_matrix_covers_the_full_20_to_100_review_range(self):
        self.assertEqual(LENGTHS[:9], (20, 29, 30, 49, 50, 79, 80, 99, 100))


if __name__ == "__main__":
    unittest.main()
