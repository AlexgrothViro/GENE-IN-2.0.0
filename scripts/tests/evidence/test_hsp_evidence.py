import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from aggregate_hsps import parse_blast
from build_hsp_evidence import FIELDS, build_hsp_evidence, _hsp_id
from common import write_tsv_atomic


def _blast_line(
    qseqid="q1",
    sseqid="ref1",
    pident="100",
    length="20",
    mismatch="0",
    gapopen="0",
    qstart="1",
    qend="20",
    sstart="10",
    send="29",
    evalue="1e-8",
    bitscore="40",
    qlen="20",
    slen="1000",
    nident="20",
    gaps="0",
) -> str:
    return "\t".join([
        qseqid, sseqid, pident, length, mismatch, gapopen,
        qstart, qend, sstart, send, evalue, bitscore, qlen, slen, nident, gaps,
    ])


class HspEvidenceTests(unittest.TestCase):
    def test_one_row_per_blast_line_with_deterministic_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            blast = Path(tmp) / "hits.tsv"
            blast.write_text(
                _blast_line() + "\n" + _blast_line(sstart="50", send="69") + "\n",
                encoding="utf-8",
            )
            records = parse_blast(blast, "blastn")
            loci = [{
                "locus_id": "LOCUS_merged",
                "sseqid": "ref1",
                "task": "blastn",
                "orientation": "+",
                "query_ids": "q1",
                "reference_intervals": "10-29;50-69",
            }]
            rows = build_hsp_evidence(records, loci)
            self.assertEqual(len(rows), 2)
            self.assertEqual([row["eligible"] for row in rows], ["true", "true"])
            expected_first = _hsp_id("blastn", records[0]["raw_fields"], 0)
            self.assertEqual(rows[0]["hsp_id"], expected_first)
            again = build_hsp_evidence(records, loci)
            self.assertEqual([r["hsp_id"] for r in again], [r["hsp_id"] for r in rows])
            for name in FIELDS:
                self.assertIn(name, rows[0])

    def test_exact_duplicate_preserved_and_ineligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            blast = Path(tmp) / "dups.tsv"
            line = _blast_line()
            blast.write_text(line + "\n" + line + "\n", encoding="utf-8")
            records = parse_blast(blast, "blastn")
            loci = [{
                "locus_id": "LOCUS_test",
                "sseqid": "ref1",
                "task": "blastn",
                "orientation": "+",
                "query_ids": "q1",
                "reference_intervals": "1-100",
            }]
            rows = build_hsp_evidence(records, loci)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["eligible"], "true")
            self.assertEqual(rows[1]["eligible"], "false")
            self.assertEqual(rows[1]["duplicate_of_hsp_id"], rows[0]["hsp_id"])
            self.assertEqual(rows[1]["rejection_reason"], "DUPLICATE_SOURCE_OBSERVATION")
            self.assertEqual(rows[1]["rule_id"], "ADMIT-HSP")
            self.assertNotEqual(rows[0]["hsp_id"], rows[1]["hsp_id"])

    def test_out_of_scope_subject_is_ineligible_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            blast = Path(tmp) / "hits.tsv"
            blast.write_text(_blast_line(sseqid="host_ref") + "\n", encoding="utf-8")
            records = parse_blast(blast, "blastn")
            rows = build_hsp_evidence(records, [])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["eligible"], "false")
            self.assertEqual(rows[0]["rejection_reason"], "OUT_OF_DECLARED_SCOPE")
            self.assertEqual(rows[0]["locus_id"], "")

    def test_zero_or_multiple_loci_fail_when_subject_has_loci(self):
        with tempfile.TemporaryDirectory() as tmp:
            blast = Path(tmp) / "hits.tsv"
            blast.write_text(_blast_line(sstart="500", send="519") + "\n", encoding="utf-8")
            records = parse_blast(blast, "blastn")
            loci_miss = [{
                "locus_id": "L1", "sseqid": "ref1", "task": "blastn",
                "orientation": "+", "query_ids": "q1",
                "reference_intervals": "1-100",
            }]
            with self.assertRaisesRegex(ValueError, "matches 0 loci"):
                build_hsp_evidence(records, loci_miss)
            blast.write_text(_blast_line() + "\n", encoding="utf-8")
            records = parse_blast(blast, "blastn")
            loci = [
                {
                    "locus_id": "L1", "sseqid": "ref1", "task": "blastn",
                    "orientation": "+", "query_ids": "q1",
                    "reference_intervals": "1-100",
                },
                {
                    "locus_id": "L2", "sseqid": "ref1", "task": "blastn",
                    "orientation": "+", "query_ids": "q1",
                    "reference_intervals": "1-100",
                },
            ]
            with self.assertRaisesRegex(ValueError, "matches 2 loci"):
                build_hsp_evidence(records, loci)

    def test_empty_blast_writes_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "hsp_evidence.tsv"
            write_tsv_atomic(out, build_hsp_evidence([], []), FIELDS)
            text = out.read_text(encoding="utf-8")
            self.assertEqual(text.strip(), "\t".join(FIELDS))


class LocusIndexRegressionTests(unittest.TestCase):
    def test_index_matches_linear_association_and_errors(self):
        from build_hsp_evidence import LocusIndex, associate_locus
        loci = [
            {"locus_id": "L1", "sseqid": "ref", "task": "blastn",
             "orientation": "+", "query_ids": "q;q;other", "reference_intervals": "1-100"},
            {"locus_id": "L2", "sseqid": "ref", "task": "blastn",
             "orientation": "+", "query_ids": "q", "reference_intervals": "90-200"},
        ]
        index = LocusIndex(loci)
        def result(hit, source):
            try:
                return associate_locus(hit, source)
            except ValueError as error:
                return str(error)
        for subject in ("ref", "absent"):
            for task in ("blastn", "blastn-short"):
                for query in ("q", "other", "missing"):
                    for start, end in ((5, 20), (95, 99), (150, 180), (250, 300), (20, 5)):
                        hit = dict(sseqid=subject, task=task, qseqid=query,
                                   qstart=1, qend=20, sstart=start, send=end)
                        with self.subTest(hit=hit):
                            self.assertEqual(result(hit, loci), result(hit, index))


if __name__ == "__main__":
    unittest.main()
