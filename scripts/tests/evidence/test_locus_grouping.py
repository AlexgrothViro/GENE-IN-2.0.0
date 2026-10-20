import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from aggregate_hsps import aggregate, load_labels, parse_blast
from build_loci import build_loci
from common import read_fasta


class LocusGroupingTests(unittest.TestCase):
    def test_multiple_overlapping_hits_form_one_locus(self):
        fixture = Path(__file__).parent / "fixtures"
        fragments = aggregate(parse_blast(fixture / "overlapping_hits.tsv", "blastn"),
                              read_fasta(fixture / "query_sequences.txt"),
                              load_labels(str(fixture / "subject_labels.tsv")))
        loci = build_loci(fragments, gap_bp=0, categories={"TARGET_VIRUS"})
        self.assertEqual(len(loci), 1)
        self.assertEqual(loci[0]["covered_reference_bp"], 70)
        self.assertEqual(loci[0]["query_count"], 2)
        self.assertGreater(loci[0]["query_covered_bp"], 0)

    def test_segments_are_automatically_independent(self):
        base = {"sseqid": "ref", "orientation": "+", "task": "blastn", "category": "TARGET_VIRUS",
                "reference_intervals": "1-20", "slen": "100", "qseqid": "q1", "sequence_sha256": "a",
                "hsp_count": "1", "best_bitscore": "50", "best_evalue": "1e-9", "qlen": "20",
                "query_intervals": "1-20"}
        loci = build_loci([dict(base, segment="A"), dict(base, segment="B", qseqid="q2")], gap_bp=100)
        self.assertEqual(len(loci), 2)


if __name__ == "__main__":
    unittest.main()
