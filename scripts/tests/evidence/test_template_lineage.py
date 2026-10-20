import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from build_template_lineage import FIELDS, build_rows_from_sam, write_header_only


class TemplateLineageTests(unittest.TestCase):
    def test_umi_mode_none_is_ineligible_with_real_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            sam = Path(tmp) / "reads.sam"
            sam.write_text(
                "@HD\tVN:1.6\tSO:unsorted\n"
                "@SQ\tSN:ref1\tLN:1000\n"
                "readA\t99\tref1\t10\t40\t10M\t=\t50\t0\tACGTACGTAC\tIIIIIIIIII\n"
                "readA\t147\tref1\t50\t40\t10M\t=\t10\t0\tACGTACGTAC\tIIIIIIIIII\n"
                "readB\t83\tref1\t20\t40\t10M\t=\t80\t0\tACGTACGTAC\tIIIIIIIIII\n"
                "readB\t163\tref1\t80\t40\t10M\t=\t20\t0\tACGTACGTAC\tIIIIIIIIII\n",
                encoding="utf-8",
            )
            loci = [{
                "locus_id": "LOCUS_1",
                "sseqid": "ref1",
                "orientation": "+",
                "query_ids": "q1",
                "reference_intervals": "1-100",
                "category": "TARGET_VIRUS",
            }]
            rows = build_rows_from_sam(
                sam,
                run_id="run-1",
                sample_id="sample-a",
                library_mode="shotgun",
                umi_mode="none",
                loci=loci,
                require_umi_tags=False,
            )
            # umi_mode=none groups by QNAME → two lineage rows
            self.assertEqual(len(rows), 2)
            by_q = {row["source_template_digests"]: row for row in rows}
            self.assertEqual(len(by_q), 2)
            for row in rows:
                self.assertEqual(row["lineage_id"], "")
                self.assertEqual(row["final_umi"], "")
                self.assertEqual(row["eligible"], "false")
                self.assertEqual(row["rejection_reason"], "MISSING_FIELD")
                self.assertEqual(row["rule_id"], "ADMIT-TEMPLATE-LINEAGE")
                self.assertEqual(int(row["template_count"]), 1)
                self.assertEqual(int(row["read_count"]), 2)
                self.assertEqual(int(row["mapped_bases"]), 20)
                self.assertEqual(int(row["proper_pair_templates"]), 1)
                self.assertEqual(int(row["discordant_templates"]), 0)

    def test_template_count_is_unique_qnames_in_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            sam = Path(tmp) / "grouped.sam"
            sam.write_text(
                "@HD\tVN:1.6\tSO:unsorted\n"
                "@SQ\tSN:ref1\tLN:1000\n"
                "r1\t99\tref1\t10\t40\t10M\t=\t50\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n"
                "r1\t147\tref1\t50\t40\t10M\t=\t10\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n"
                "r2\t99\tref1\t12\t40\t10M\t=\t52\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n"
                "r2\t147\tref1\t52\t40\t10M\t=\t12\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n",
                encoding="utf-8",
            )
            loci = [{
                "locus_id": "LOCUS_1",
                "sseqid": "ref1",
                "orientation": "+",
                "query_ids": "q1",
                "reference_intervals": "1-100",
            }]
            rows = build_rows_from_sam(
                sam,
                run_id="run-1",
                sample_id="sample-a",
                library_mode="shotgun",
                umi_mode="tag",
                loci=loci,
                require_umi_tags=True,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(int(rows[0]["template_count"]), 2)
            self.assertEqual(int(rows[0]["proper_pair_templates"]), 2)
            self.assertEqual(int(rows[0]["discordant_templates"]), 0)
            self.assertEqual(int(rows[0]["read_count"]), 4)

    def test_mate_without_tags_recovers_from_mate_with_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            sam = Path(tmp) / "partial_tags.sam"
            # Mate 1 has UG/BX; mate 2 (still in locus) has none — resolve from mate 1.
            sam.write_text(
                "@HD\tVN:1.6\tSO:unsorted\n"
                "@SQ\tSN:ref1\tLN:1000\n"
                "r1\t99\tref1\t10\t40\t10M\t=\t50\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:9\tBX:Z:BBBB\n"
                "r1\t147\tref1\t50\t40\t10M\t=\t10\t0\tACGTACGTAC\tIIIIIIIIII\n",
                encoding="utf-8",
            )
            loci = [{
                "locus_id": "LOCUS_1",
                "sseqid": "ref1",
                "orientation": "+",
                "query_ids": "q1",
                "reference_intervals": "1-100",
            }]
            rows = build_rows_from_sam(
                sam,
                run_id="run-1",
                sample_id="sample-a",
                library_mode="shotgun",
                umi_mode="tag",
                loci=loci,
                require_umi_tags=True,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["eligible"], "true")
            self.assertEqual(rows[0]["final_umi"], "BBBB")
            self.assertEqual(int(rows[0]["template_count"]), 1)
            self.assertEqual(int(rows[0]["read_count"]), 2)

    def test_umi_group_rows_are_eligible_and_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            sam = Path(tmp) / "grouped.sam"
            sam.write_text(
                "@HD\tVN:1.6\tSO:unsorted\n"
                "@SQ\tSN:ref1\tLN:1000\n"
                "r1\t99\tref1\t10\t40\t10M\t=\t50\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n"
                "r2\t147\tref1\t50\t40\t10M\t=\t10\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n",
                encoding="utf-8",
            )
            loci = [{
                "locus_id": "LOCUS_1",
                "sseqid": "ref1",
                "orientation": "+",
                "query_ids": "q1",
                "reference_intervals": "1-100",
                "category": "TARGET_VIRUS",
            }]
            first = build_rows_from_sam(
                sam,
                run_id="run-1",
                sample_id="sample-a",
                library_mode="shotgun",
                umi_mode="tag",
                loci=loci,
                require_umi_tags=True,
            )
            second = build_rows_from_sam(
                sam,
                run_id="run-1",
                sample_id="sample-a",
                library_mode="shotgun",
                umi_mode="tag",
                loci=loci,
                require_umi_tags=True,
            )
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["eligible"], "true")
            self.assertEqual(first[0]["final_umi"], "AAAA")
            self.assertEqual(int(first[0]["template_count"]), 2)
            self.assertEqual(len(first[0]["lineage_id"]), 64)
            self.assertEqual(first[0]["lineage_id"], second[0]["lineage_id"])
            self.assertEqual(first[0]["lineage_record_id"], second[0]["lineage_record_id"])

    def test_missing_ug_bx_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            sam = Path(tmp) / "bad.sam"
            sam.write_text(
                "@HD\tVN:1.6\n@SQ\tSN:ref1\tLN:1000\n"
                "r1\t99\tref1\t10\t40\t10M\t=\t50\t0\tACGTACGTAC\tIIIIIIIIII\n",
                encoding="utf-8",
            )
            loci = [{
                "locus_id": "LOCUS_1", "sseqid": "ref1", "orientation": "+",
                "query_ids": "q1", "reference_intervals": "1-100",
            }]
            with self.assertRaisesRegex(ValueError, "missing UG/BX"):
                build_rows_from_sam(
                    sam,
                    run_id="run-1",
                    sample_id="sample-a",
                    library_mode="shotgun",
                    umi_mode="tag",
                    loci=loci,
                    require_umi_tags=True,
                )

    def test_orphan_and_discordant_pair_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            sam = Path(tmp) / "geometry.sam"
            # orphan: paired (0x1) + mate unmapped (0x8) → flag 73 = 64+8+1
            # discordant: paired without proper (0x1, no 0x2) → flag 65
            # proper: flag 99
            sam.write_text(
                "@HD\tVN:1.6\tSO:unsorted\n"
                "@SQ\tSN:ref1\tLN:1000\n"
                "orphan1\t73\tref1\t10\t40\t10M\t*\t0\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n"
                "disc1\t65\tref1\t20\t40\t10M\tref1\t500\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:2\tBX:Z:BBBB\n"
                "disc1\t129\tref1\t500\t40\t10M\tref1\t20\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:2\tBX:Z:BBBB\n"
                "prop1\t99\tref1\t30\t40\t10M\t=\t70\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:3\tBX:Z:CCCC\n"
                "prop1\t147\tref1\t70\t40\t10M\t=\t30\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:3\tBX:Z:CCCC\n",
                encoding="utf-8",
            )
            loci = [{
                "locus_id": "LOCUS_1",
                "sseqid": "ref1",
                "orientation": "+",
                "query_ids": "q1",
                "reference_intervals": "1-600",
            }]
            rows = build_rows_from_sam(
                sam,
                run_id="run-1",
                sample_id="sample-a",
                library_mode="shotgun",
                umi_mode="tag",
                loci=loci,
                require_umi_tags=True,
            )
            by_umi = {row["final_umi"]: row for row in rows}
            self.assertEqual(int(by_umi["AAAA"]["template_count"]), 1)
            self.assertEqual(int(by_umi["AAAA"]["read_count"]), 1)
            self.assertEqual(int(by_umi["AAAA"]["proper_pair_templates"]), 0)
            self.assertEqual(int(by_umi["AAAA"]["discordant_templates"]), 1)
            self.assertEqual(int(by_umi["BBBB"]["template_count"]), 1)
            self.assertEqual(int(by_umi["BBBB"]["discordant_templates"]), 1)
            self.assertEqual(int(by_umi["BBBB"]["proper_pair_templates"]), 0)
            self.assertEqual(int(by_umi["CCCC"]["proper_pair_templates"]), 1)
            self.assertEqual(int(by_umi["CCCC"]["discordant_templates"]), 0)

    def test_inconsistent_ug_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            sam = Path(tmp) / "bad_ug.sam"
            sam.write_text(
                "@HD\tVN:1.6\n@SQ\tSN:ref1\tLN:1000\n"
                "r1\t99\tref1\t10\t40\t10M\t=\t50\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:1\tBX:Z:AAAA\n"
                "r1\t147\tref1\t50\t40\t10M\t=\t10\t0\tACGTACGTAC\tIIIIIIIIII\tUG:Z:2\tBX:Z:AAAA\n",
                encoding="utf-8",
            )
            loci = [{
                "locus_id": "LOCUS_1", "sseqid": "ref1", "orientation": "+",
                "query_ids": "q1", "reference_intervals": "1-100",
            }]
            with self.assertRaisesRegex(ValueError, "inconsistent UG"):
                build_rows_from_sam(
                    sam,
                    run_id="run-1",
                    sample_id="sample-a",
                    library_mode="shotgun",
                    umi_mode="tag",
                    loci=loci,
                    require_umi_tags=True,
                )

    def test_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "template_lineage.tsv"
            write_header_only(out)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "\t".join(FIELDS))


if __name__ == "__main__":
    unittest.main()
