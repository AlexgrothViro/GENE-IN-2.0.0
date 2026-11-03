"""Regression tests for ACTIONABLE counts and preserved audit evidence.

REVIEW rows stay visible with their original class, reference, and raw values,
while only ACTIONABLE rows contribute to the canonical claim count.
"""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pipeline" / "export_hit_contigs.py"

LABELED_HEADER = [
    "qseqid", "sseqid", "pident", "length", "evalue", "bitscore",
    "qlen", "aln_cov", "adj_identity", "evidence_class", "risk_note",
]


def run_export(tmp: Path, sample: str, rows: list[list[str]], contig_seqs: dict[str, str],
               control_status: str | None = None):
    labeled = tmp / "labeled_hits.tsv"
    contigs = tmp / "contigs.fa"
    out_dir = tmp / "out"
    with labeled.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(LABELED_HEADER)
        writer.writerows(rows)
    with contigs.open("w", encoding="utf-8") as handle:
        for name, seq in contig_seqs.items():
            handle.write(f">{name}\n{seq}\n")
    command = [sys.executable, str(SCRIPT), "--labeled", str(labeled), "--contigs", str(contigs),
               "--sample", sample, "--out-dir", str(out_dir)]
    if control_status:
        command += ["--control-status", control_status]
    result = subprocess.run(command, capture_output=True, text=True)
    summary_path = out_dir / f"{sample}_hit_contigs_summary.tsv"
    fasta_path = out_dir / f"{sample}_hit_contigs.fa"
    return result, summary_path, fasta_path


def read_summary_rows(summary_path: Path) -> list[dict]:
    with summary_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class ConfidenceTierTests(unittest.TestCase):
    def test_review_only_contig_is_preserved_for_audit_and_excluded_from_claim_count(self):
        """Regression fixture: DEV_NEIGHBOR_EMCV single REVIEW hit."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [[
                "NODE_1_length_7642_cov_2.817713", "ref|NC_011349.1|", "72.34", "282",
                "7.99e-38", "150.0", "7642", "0.03677", "2.66", "REVIEW",
                "baixa_identidade_ajustada",
            ]]
            result, summary_path, fasta_path = run_export(
                tmp, "DEV_NEIGHBOR_EMCV",
                rows, {"NODE_1_length_7642_cov_2.817713": "ACGT" * 20},
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            summary_rows = read_summary_rows(summary_path)
            self.assertEqual(len(summary_rows), 1, "REVIEW hit must not be silently dropped")
            row = summary_rows[0]
            # Not reclassified: evidence_class is preserved exactly as computed
            # by label_hits.py.
            self.assertEqual(row["evidence_class"], "REVIEW")
            # Separate audit tier; evidence_class remains the original label.
            self.assertEqual(row["confidence_tier"], "REVIEW")
            # best_ref (the accession named in the claim) is preserved for audit,
            # not erased.
            self.assertEqual(row["best_ref"], "ref|NC_011349.1|")
            self.assertEqual(row["pident"], "72.340")
            self.assertEqual(row["aln_cov"], "0.03677")
            self.assertEqual(row["adj_identity"], "2.660")
            self.assertEqual(row["evalue"], "7.99e-38")
            self.assertEqual(row["bitscore"], "150.0")
            self.assertIn("EXPORT_HIT_CONTIGS_CANONICAL_CLAIM_COUNT=0", result.stdout)

            fasta_text = fasta_path.read_text(encoding="utf-8")
            self.assertIn("confidence_tier=REVIEW", fasta_text)
            self.assertIn("evidence_class=REVIEW", fasta_text)

    def test_strong_hit_is_tagged_actionable_no_regression(self):
        """A hit at or above MODERATE must remain an unmarked, actionable claim."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [[
                "NODE_1_strong", "ref|NC_003985.1|", "99.0", "7090", "1e-200",
                "10000.0", "7090", "1.0", "99.0", "STRONG", "ok",
            ]]
            result, summary_path, _ = run_export(
                tmp, "DEV_PTV_HIGH", rows, {"NODE_1_strong": "ACGT" * 20},
                control_status="CONTROL_BELOW_SAMPLE",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary_rows = read_summary_rows(summary_path)
            self.assertEqual(len(summary_rows), 1)
            self.assertEqual(summary_rows[0]["evidence_class"], "STRONG")
            self.assertEqual(summary_rows[0]["confidence_tier"], "ACTIONABLE")

    def test_weak_recoverable_is_preserved_for_review_without_promotion(self):
        """The new recovery version preserves weak sequences outside ACTIONABLE."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                ["NODE_A", "ref|A|", "85.0", "5000", "1e-100", "5000.0", "6000", "0.90", "76.5", "STRONG_DIVERGENT", "ok"],
                ["NODE_B", "ref|B|", "86.0", "60", "1e-6", "60.0", "60", "1.0", "86.0", "MODERATE", "ok"],
                ["NODE_C", "ref|C|", "91.0", "25", "1e-6", "40.0", "25", "1.0", "91.0", "WEAK_RECOVERABLE", "fragmento_curto_exige_revisao"],
            ]
            result, summary_path, _ = run_export(
                tmp, "MIXED_CLASSES", rows,
                {"NODE_A": "ACGT" * 1500, "NODE_B": "ACGT" * 15, "NODE_C": "ACGT" * 7},
                control_status="CONTROL_NOT_DETECTED",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary_rows = {r["qseqid"]: r for r in read_summary_rows(summary_path)}
            for qseqid, expected_class in (
                ("NODE_A", "STRONG_DIVERGENT"), ("NODE_B", "MODERATE"), ("NODE_C", "WEAK_RECOVERABLE"),
            ):
                self.assertEqual(summary_rows[qseqid]["evidence_class"], expected_class)
                expected_tier = "REVIEW" if expected_class == "WEAK_RECOVERABLE" else "ACTIONABLE"
                self.assertEqual(summary_rows[qseqid]["confidence_tier"], expected_tier)

    def test_review_hit_never_wins_over_an_actionable_hit_on_the_same_contig(self):
        """A weak secondary REVIEW hit on an ACTIONABLE contig must not
        replace the ACTIONABLE row selected for the contig; class priority
        already
        guarantees this; this test locks that guarantee in against the new
        confidence_tier column."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                ["NODE_1", "ref|NC_003985.1|", "99.0", "7090", "1e-200", "10000.0", "7090", "1.0", "99.0", "STRONG", "ok"],
                ["NODE_1", "ref|NC_999999.1|", "70.0", "100", "1e-5", "50.0", "7090", "0.01", "0.7", "REVIEW", "baixa_identidade_ajustada"],
            ]
            result, summary_path, _ = run_export(
                tmp, "DEV_PTV_HIGH_MIXED", rows, {"NODE_1": "ACGT" * 20},
                control_status="CONTROL_BELOW_SAMPLE",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary_rows = read_summary_rows(summary_path)
            self.assertEqual(len(summary_rows), 1, "one audit row per contig")
            self.assertEqual(summary_rows[0]["evidence_class"], "STRONG")
            self.assertEqual(summary_rows[0]["confidence_tier"], "ACTIONABLE")
            self.assertEqual(summary_rows[0]["best_ref"], "ref|NC_003985.1|")
            self.assertEqual(summary_rows[0]["pident"], "99.000")
            self.assertIn("EXPORT_HIT_CONTIGS_CANONICAL_CLAIM_COUNT=1", result.stdout)

    def test_discordant_evidence_class_is_preserved_and_excluded_from_claim_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [["NODE_D", "ref|D|", "80.0", "100", "1e-5", "50.0", "120", "0.8", "64.0", "DISCORDANT", "conflito"]]
            result, summary_path, _ = run_export(tmp, "DISCORDANT_AUDIT", rows, {"NODE_D": "ACGT" * 30})
            self.assertEqual(result.returncode, 0, result.stderr)
            row = read_summary_rows(summary_path)[0]
            self.assertEqual(row["evidence_class"], "DISCORDANT")
            self.assertEqual(row["confidence_tier"], "DISCORDANT")
            self.assertEqual(row["best_ref"], "ref|D|")
            self.assertIn("EXPORT_HIT_CONTIGS_CANONICAL_CLAIM_COUNT=0", result.stdout)

    def test_unrecognized_class_named_actionable_cannot_enter_claim_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [["NODE_U", "ref|U|", "80.0", "100", "1e-5", "50.0", "120", "0.8", "64.0", "ACTIONABLE", "unknown"]]
            result, summary_path, _ = run_export(tmp, "UNKNOWN_CLASS", rows, {"NODE_U": "ACGT" * 30})
            self.assertEqual(result.returncode, 0, result.stderr)
            row = read_summary_rows(summary_path)[0]
            self.assertEqual(row["evidence_class"], "ACTIONABLE")
            self.assertEqual(row["confidence_tier"], "UNCLASSIFIED")
            self.assertIn("EXPORT_HIT_CONTIGS_CANONICAL_CLAIM_COUNT=0", result.stdout)

    def test_uncontrolled_strong_hit_stays_review(self):
        """Without a validated control, a STRONG class does not become ACTIONABLE."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [[
                "NODE_1_strong", "ref|NC_003985.1|", "99.0", "7090", "1e-200",
                "10000.0", "7090", "1.0", "99.0", "STRONG", "ok",
            ]]
            result, summary_path, _ = run_export(
                tmp, "UNCONTROLLED_STRONG", rows, {"NODE_1_strong": "ACGT" * 20},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            row = read_summary_rows(summary_path)[0]
            self.assertEqual(row["evidence_class"], "STRONG")
            self.assertEqual(row["confidence_tier"], "REVIEW")
            self.assertIn("EXPORT_HIT_CONTIGS_CANONICAL_CLAIM_COUNT=0", result.stdout)
            self.assertNotIn("ACTIONABLE", result.stdout)

    def test_no_hits_summary_header_still_declares_confidence_tier(self):
        """The header-only empty-result contract also carries the new column,
        so a downstream reader never has to special-case an empty run."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            result, summary_path, fasta_path = run_export(tmp, "DEV_NEG_RANDOM", [], {})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(fasta_path.exists())
            self.assertEqual(fasta_path.read_text(encoding="utf-8"), "")
            with summary_path.open("r", encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle, delimiter="\t"))
            self.assertIn("confidence_tier", header)
            self.assertIn("evidence_class", header)


if __name__ == "__main__":
    unittest.main()
