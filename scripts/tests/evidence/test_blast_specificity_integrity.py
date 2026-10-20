import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from aggregate_hsps import aggregate, load_labels, parse_blast
from blast_router import (database_report_limit, deduplicate_combined_files, deduplicate_combined_hits,
                          run_router)
from build_loci import build_loci
from classify_sample import classify
from competitive_hits import evaluate


def fragment_hit(subject, category, score, qcov=0.9):
    return {
        "qseqid": "q",
        "sseqid": subject,
        "category": category,
        "taxon": subject,
        "task": "blastn",
        "best_bitscore": str(score),
        "query_coverage": str(qcov),
        "low_complexity_status": "ACCEPTABLE",
    }


class BlastSpecificityIntegrityTests(unittest.TestCase):
    def test_database_report_limit_covers_small_and_large_panels(self):
        self.assertEqual(database_report_limit("panel", sequence_count=7), 50)
        self.assertEqual(database_report_limit("panel", sequence_count=61), 61)

    def test_legacy_pipeline_uses_database_wide_report_limit(self):
        pipeline = "\n".join((ROOT / "scripts/pipeline" / part).read_text(encoding="utf-8") for part in ("prepare_run.sh", "sample_steps.sh", "run.sh"))
        self.assertIn("database_report_limit", pipeline)
        self.assertIn('-max_target_seqs "$BLAST_REPORT_LIMIT"', pipeline)
        self.assertNotIn("-max_target_seqs 10", pipeline)

    def test_dual_profile_dedup_keeps_strongest_exact_coordinate_hit(self):
        weak = "q\ts\t90\t20\t2\t0\t1\t20\t10\t29\t1e-2\t20\t30\t100\t18\t0\n"
        strong = "q\ts\t100\t20\t0\t0\t1\t20\t10\t29\t1e-8\t40\t30\t100\t20\t0\n"
        result = deduplicate_combined_hits([weak, strong]).strip().split("\t")
        self.assertEqual(float(result[11]), 40.0)

    def test_dedup_does_not_collapse_distinct_query_intervals(self):
        first = "q\ts\t95\t20\t1\t0\t1\t20\t10\t29\t1e-5\t30\t40\t100\t19\t0\n"
        second = "q\ts\t95\t20\t1\t0\t21\t40\t10\t29\t1e-5\t30\t40\t100\t19\t0\n"
        self.assertEqual(len(deduplicate_combined_hits([first, second]).splitlines()), 2)

    def test_streaming_dedup_is_byte_identical_to_in_memory_dedup(self):
        # Regression for the read-level rescue OOM: the combined report must be
        # produced without loading the BLAST reports, with the same bytes.
        def row(q, s, qs, qe, ss, se, ev, bits, pid="95.000"):
            return f"{q}\t{s}\t{pid}\t20\t1\t0\t{qs}\t{qe}\t{ss}\t{se}\t{ev}\t{bits}\t40\t100\t19\t0\n"
        short = (row("q1", "s1", 1, 20, 10, 29, "1e-2", 20) + row("q1", "s2", 1, 20, 50, 31, "5", 15)
                 + row("q3", "s1", 2, 21, 11, 30, "3", 16))
        conventional = (row("q1", "s1", 1, 20, 10, 29, "1e-8", 40) + row("q1", "s3", 5, 25, 1, 21, "2", 18)
                        + row("q2", "s1", 1, 20, 10, 29, "1e-3", 22) + row("q3", "s1", 2, 21, 11, 30, "3", 16)
                        + row("q3", "s2", 2, 21, 30, 11, "9", 12))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "short.tsv").write_text(short, encoding="utf-8")
            (root / "conventional.tsv").write_text(conventional, encoding="utf-8")
            out = root / "combined.tsv"
            deduplicate_combined_files([root / "short.tsv", root / "conventional.tsv"], ["q1", "q2", "q3"], out)
            self.assertEqual(out.read_text(encoding="utf-8"), deduplicate_combined_hits([short, conventional]))
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["combined.tsv", "conventional.tsv", "short.tsv"])

    def test_malformed_coordinates_are_rejected_before_aggregation(self):
        line = "q\ts\t99\t20\t0\t0\t1\t40\t1\t20\t1e-5\t50\t20\t100\t20\t0\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.tsv"
            path.write_text(line, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "coordinates exceed"):
                parse_blast(path, "blastn")

    def test_legacy_14_column_blast_is_rejected(self):
        line = "q\ts\t100\t20\t0\t0\t1\t20\t10\t29\t1e-8\t40\t30\t100\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.tsv"
            path.write_text(line, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy 14-column"):
                parse_blast(path, "blastn")

    def test_nident_mismatch_gaps_must_equal_length(self):
        line = "q\ts\t100\t20\t0\t0\t1\t20\t10\t29\t1e-8\t40\t30\t100\t19\t0\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_counts.tsv"
            path.write_text(line, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nident \\+ mismatch \\+ gaps"):
                parse_blast(path, "blastn")

    def test_disconnected_reference_hsps_remain_separate_fragments(self):
        common = {
            "qseqid": "q",
            "sseqid": "ref",
            "task": "blastn",
            "pident": 100.0,
            "length": 20,
            "mismatch": 0,
            "gapopen": 0,
            "evalue": 1e-8,
            "bitscore": 40.0,
            "qlen": 100,
            "slen": 1000,
        }
        records = [
            dict(common, qstart=1, qend=20, sstart=1, send=20),
            dict(common, qstart=81, qend=100, sstart=500, send=519),
        ]
        rows = aggregate(records, {"q": "ACGT" * 25}, {})
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["query_covered_bp"] for row in rows], [20, 20])

    def test_locus_query_coverage_is_scoped_per_query(self):
        base = {
            "sseqid": "ref",
            "segment": "u",
            "orientation": "+",
            "task": "blastn",
            "category": "TARGET_VIRUS",
            "slen": "1000",
            "hsp_count": "1",
            "best_bitscore": "50",
            "sum_bitscore": "50",
            "best_evalue": "1e-5",
            "adj_identity": "80",
            "low_complexity_status": "ACCEPTABLE",
            "qlen": "20",
        }
        rows = [
            dict(
                base,
                qseqid="q1",
                reference_intervals="1-20",
                query_intervals="1-20",
                query_covered_bp="20",
                sequence_sha256="a",
            ),
            dict(
                base,
                qseqid="q2",
                reference_intervals="10-29",
                query_intervals="1-20",
                query_covered_bp="20",
                sequence_sha256="b",
            ),
        ]
        locus = build_loci(rows, gap_bp=0)[0]
        self.assertEqual(locus["query_covered_bp"], 40)
        self.assertEqual(locus["max_query_covered_bp"], 20)
        self.assertEqual(locus["query_intervals"], "q1:1-20|q2:1-20")

    def test_candidate_length_uses_aligned_query_span(self):
        locus = {
            "locus_id": "L1",
            "sseqid": "virus",
            "category": "TARGET_VIRUS",
            "query_ids": "q",
            "orientation": "+",
            "task": "blastn",
            "covered_reference_bp": "20",
            "max_query_length": "100",
            "max_query_covered_bp": "20",
            "reference_intervals": "1-20",
        }
        competitive = {
            "qseqid": "q",
            "task": "blastn",
            "specificity_status": "TARGET_SPECIFIC",
        }
        result = classify(
            "synthetic", [locus], [competitive], [], [], "UNCONTROLLED", "shotgun"
        )
        self.assertEqual(result["promotion_gates"], [])
        self.assertEqual(result["candidates"][0]["promotion_status"], "AVAILABLE")

    def test_unlabeled_hit_blocks_target_specificity(self):
        result = evaluate(
            [
                fragment_hit("target", "TARGET_VIRUS", 100),
                fragment_hit("host", "HOST", 80),
                fragment_hit("unknown", "UNLABELED", 99),
            ]
        )[0]
        self.assertEqual(result["specificity_status"], "AMBIGUOUS")
        self.assertIn("UNLABELED_HIT_PRESENT", result["specificity_flags"])

    def test_unverified_external_search_cannot_be_target_specific(self):
        result = evaluate(
            [
                fragment_hit("target", "TARGET_VIRUS", 100),
                fragment_hit("host", "HOST", 80),
            ],
            search_complete=False,
        )[0]
        self.assertNotEqual(result["specificity_status"], "TARGET_SPECIFIC")
        self.assertIn("SEARCH_SPACE_UNVERIFIED", result["specificity_flags"])

    def test_duplicate_subject_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.tsv"
            path.write_text(
                "sseqid\tcategory\nref\tTARGET_VIRUS\nref\tHOST\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_labels(str(path))


@unittest.skipUnless(
    all(shutil.which(name) for name in ("blastn", "blastdbcmd", "makeblastdb")),
    "NCBI BLAST+ tools are not installed",
)
class RealBlastRouterTests(unittest.TestCase):
    def test_report_limit_covers_every_competitive_subject(self):
        config = {
            "blast": {
                "short_max_bp": 29,
                "dual_mode_min_bp": 30,
                "dual_mode_max_bp": 49,
                "explicit_dust": False,
                "soft_masking": True,
            }
        }
        query_sequence = "ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGC"
        subject_sequence = query_sequence + "TGCATCGATCGTACGTAGCTAGCATGCTACGT"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "panel.fa"
            reference.write_text(
                "".join(
                    f">subject_{index:03d}\n{subject_sequence}\n"
                    for index in range(61)
                ),
                encoding="utf-8",
            )
            query = root / "query.fa"
            query.write_text(f">query\n{query_sequence}\n", encoding="utf-8")
            database = root / "panel"
            subprocess.run(
                [
                    shutil.which("makeblastdb"),
                    "-in",
                    str(reference),
                    "-dbtype",
                    "nucl",
                    "-parse_seqids",
                    "-out",
                    str(database),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            short = root / "short.tsv"
            conventional = root / "conventional.tsv"
            provenance = run_router(
                str(query),
                str(database),
                config,
                1,
                short,
                conventional,
                None,
            )
            self.assertEqual(provenance["database_sequence_count"], 61)
            self.assertGreaterEqual(
                provenance["profiles"]["short"]["max_target_seqs"], 61
            )

    def test_database_path_containing_spaces_is_searched_as_one_database(self):
        # BLAST+'s own -db argument parser reads unquoted whitespace as a
        # database-list separator, so a database prefix living under a
        # directory with a space (a real kit path did) must still resolve
        # to exactly one database via blast_db_arg(), not be silently
        # misread as multiple missing databases.
        query_sequence = "ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGC"
        subject_sequence = query_sequence + "TGCATCGATCGTACGTAGCTAGCATGCTACGT"
        with tempfile.TemporaryDirectory() as tmp:
            build_root = Path(tmp) / "build"
            build_root.mkdir()
            reference = build_root / "panel.fa"
            reference.write_text(f">subject_001\n{subject_sequence}\n", encoding="utf-8")
            build_database = build_root / "panel"
            subprocess.run(
                [shutil.which("makeblastdb"), "-in", str(reference), "-dbtype", "nucl",
                 "-parse_seqids", "-out", str(build_database)],
                check=True, capture_output=True, text=True,
            )
            spaced_root = Path(tmp) / "external output with spaces"
            spaced_root.mkdir()
            for artifact in build_root.glob("panel.*"):
                shutil.copy2(artifact, spaced_root / artifact.name)
            spaced_database = spaced_root / "panel"

            self.assertEqual(
                database_report_limit(str(spaced_database), shutil.which("blastdbcmd")), 50,
            )

            query = spaced_root / "query.fa"
            query.write_text(f">query\n{query_sequence}\n", encoding="utf-8")
            short = spaced_root / "short.tsv"
            conventional = spaced_root / "conventional.tsv"
            provenance = run_router(
                str(query), str(spaced_database),
                {"blast": {"short_max_bp": 29, "dual_mode_min_bp": 30, "dual_mode_max_bp": 49,
                           "explicit_dust": False, "soft_masking": True}},
                1, short, conventional, None,
            )
            self.assertEqual(provenance["database_sequence_count"], 1)


if __name__ == "__main__":
    unittest.main()
