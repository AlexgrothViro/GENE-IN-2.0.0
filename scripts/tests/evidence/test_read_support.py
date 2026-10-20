import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from summarize_read_support import five_prime, summarize_sam


class ReadSupportTests(unittest.TestCase):
    def test_r1_r2_are_one_template(self):
        sam = (
            "pair1\t99\tref\t10\t40\t20M\t=\t100\t110\tACGT\tIIII\n"
            "pair1\t147\tref\t100\t40\t20M\t=\t10\t-110\tACGT\tIIII\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reads.sam"
            path.write_text(sam, encoding="utf-8")
            row = summarize_sam(str(path), "synthetic", "shotgun", "none", 10)[0]
        self.assertEqual(row["unique_templates"], 1)
        self.assertEqual(row["proper_pair_templates"], 1)
        self.assertEqual(row["distinct_starts"], 2)

    def test_secondary_supplementary_low_mapq_and_unmapped_are_ignored(self):
        sam = (
            "valid\t99\tref\t10\t40\t5S15M\t=\t100\t110\tACGT\tIIII\n"
            "valid\t147\tref\t100\t40\t20M\t=\t10\t-110\tACGT\tIIII\n"
            "secondary\t355\tref\t20\t50\t20M\t=\t120\t0\tACGT\tIIII\n"
            "supplementary\t2147\tref\t30\t50\t20M\t=\t130\t0\tACGT\tIIII\n"
            "lowmapq\t99\tref\t40\t5\t20M\t=\t140\t0\tACGT\tIIII\n"
            "unmapped\t77\t*\t0\t0\t*\t*\t0\t0\tACGT\tIIII\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "flags.sam"
            path.write_text(sam, encoding="utf-8")
            row = summarize_sam(str(path), "synthetic", "shotgun", "none", 10)[0]
        self.assertEqual(row["unique_templates"], 1)
        self.assertEqual(row["proper_pair_templates"], 1)
        self.assertEqual(five_prime(10, "5S15M", False), 5)
        self.assertEqual(five_prime(100, "15M5S", True), 119)

    def test_discordant_pair_is_reported_without_becoming_proper(self):
        sam = (
            "pair2\t97\tref\t10\t40\t20M\tother\t100\t0\tACGT\tIIII\n"
            "pair2\t145\tother\t100\t40\t20M\tref\t10\t0\tACGT\tIIII\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discordant.sam"
            path.write_text(sam, encoding="utf-8")
            row = summarize_sam(str(path), "synthetic", "shotgun", "none", 10)[0]
        self.assertEqual(row["proper_pair_templates"], 0)
        self.assertEqual(row["discordant_templates"], 1)


if __name__ == "__main__":
    unittest.main()
