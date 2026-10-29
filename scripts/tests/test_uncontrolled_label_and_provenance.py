"""Label ceiling and recorded BLAST parameters.

An execution without a validated control stays at REVIEW. Builder records
shorter than 200 bp are marked in candidate_summary.tsv. Random synthetic
input does not receive DETECTED. Provenance copies the effective BLAST
values already stored in the search profile.
"""
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))

from classify_sample import classify
from competitive_hits import evaluate
from export_candidate_sequences import _summary_rows
from export_hit_contigs import confidence_tier_for
from search_profile_manifest import effective_blast_record
from write_provenance import EFFECTIVE_BLAST_KEYS, apply_effective_blast


def _locus(query: str = "q", length: str = "80") -> dict:
    return {
        "locus_id": "L1",
        "sseqid": "synthetic-virus",
        "query_ids": query,
        "orientation": "+",
        "task": "blastn",
        "category": "TARGET_VIRUS",
        "covered_reference_bp": length,
        "max_query_length": length,
        "max_query_covered_bp": length,
        "reference_intervals": f"1-{length}",
        "reference_length": "200",
    }


class UncontrolledLabelTests(unittest.TestCase):
    def test_uncontrolled_candidates_stay_review(self):
        value = classify("sample", [_panel_locus()], [], [], [], "UNCONTROLLED", "shotgun")
        self.assertEqual(value["analysis_outcome"], "CANDIDATES_FOR_REVIEW")
        self.assertEqual(value["evidence_level"], "REVIEW")
        self.assertNotIn("DETECTED", json.dumps(value))
        self.assertNotIn("ACTIONABLE", json.dumps(value))

    def test_validated_control_can_carry_detected(self):
        value = classify(
            "sample", [_panel_locus()], [], [], [], "CONTROL_BELOW_SAMPLE", "shotgun",
        )
        self.assertEqual(value["evidence_level"], "DETECTED")
        self.assertEqual(value["analysis_outcome"], "EVIDENCE_RECOVERED")

    def test_random_synthetic_input_has_zero_detected(self):
        rng = random.Random(20261029)
        alphabet = "ACGT"
        for index in range(12):
            length = rng.randint(20, 180)
            query = "".join(rng.choice(alphabet) for _ in range(length))
            self.assertGreaterEqual(len(query), 20)
            value = classify(
                f"random-{index}",
                [_locus(query=f"q{index}", length=str(length))],
                [],
                [],
                [],
                "UNCONTROLLED",
                "shotgun",
            )
            blob = json.dumps(value)
            self.assertEqual(blob.count("DETECTED"), 0, blob)
            self.assertNotIn("ACTIONABLE", blob)
            self.assertEqual(value["evidence_level"], "REVIEW")

    def test_builder_records_below_200_bp_are_marked_review(self):
        grouped = {
            "short": {
                "best": {
                    "qseqid": "short",
                    "sequence_length_bp": 80,
                    "assembly_method": "builder",
                    "sseqid": "ref",
                    "taxon": "",
                    "best_evalue": "1e-5",
                },
                "rank": (0,),
                "count": 1,
                "min_number": 1.0,
                "min_text": "1e-5",
            },
            "long": {
                "best": {
                    "qseqid": "long",
                    "sequence_length_bp": 240,
                    "assembly_method": "builder",
                    "sseqid": "ref",
                    "taxon": "taxon",
                    "best_evalue": "1e-20",
                },
                "rank": (0,),
                "count": 1,
                "min_number": 1.0,
                "min_text": "1e-20",
            },
        }
        rows = {row["qseqid"]: row for row in _summary_rows(grouped, {})}
        self.assertEqual(rows["short"]["fragmento_curto"], "true")
        self.assertEqual(rows["short"]["rotulo"], "REVIEW")
        self.assertEqual(rows["long"]["fragmento_curto"], "false")
        self.assertEqual(rows["long"]["rotulo"], "CANDIDATO")

    def test_search_profile_fills_unknown_blast_parameters(self):
        record = effective_blast_record(
            {"blast_task": "blastn", "blast_evalue": "1e-5", "blast_word_size": 11},
            max_target_seqs="50",
            database_sequence_count="4",
        )
        values = {key: "unknown" for key in EFFECTIVE_BLAST_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "search_profile.json"
            path.write_text(json.dumps({"effective_blast": record}), encoding="utf-8")
            apply_effective_blast(values, path)
        self.assertEqual(values["blast_evalue"], "1e-5")
        self.assertEqual(values["blastn_word_size"], "11")
        self.assertEqual(values["blast_gapopen"], "5")
        self.assertEqual(values["blast_gapextend"], "2")
        self.assertEqual(values["blastn_reward"], "2")
        self.assertEqual(values["blastn_penalty"], "-3")
        self.assertEqual(values["blast_max_target_seqs"], "50")
        self.assertEqual(values["blast_database_sequence_count"], "4")
        self.assertNotIn("unknown", values.values())


def _hit(subject, taxon, score, category="TARGET_VIRUS", task="blastn"):
    return {
        "qseqid": "q", "sseqid": subject, "taxon": taxon, "best_bitscore": str(score),
        "query_coverage": "1.0", "low_complexity_status": "ACCEPTABLE",
        "category": category, "task": task,
    }


def _panel_locus():
    return {
        "locus_id": "L1", "sseqid": "A", "taxon": "taxon-A", "query_ids": "q",
        "category": "TARGET_VIRUS", "reference_intervals": "1-20",
        "reference_length": "100", "covered_reference_bp": "20",
        "max_query_length": "20", "max_query_covered_bp": "20",
        "orientation": "+", "task": "blastn",
    }


class LabelRegressionTests(unittest.TestCase):
    def test_detected_label_keeps_non_target_and_other_caveats(self):
        competitive = evaluate([
            _hit("A", "taxon-A", 20),
            _hit("host", "host", 40, "HOST"),
        ])
        value = classify("sample", [_panel_locus()], competitive, [], [], "CONTROL_BELOW_SAMPLE", "shotgun")
        self.assertEqual(value["evidence_level"], "DETECTED")
        text = "\n".join(value["caveats"])
        self.assertIn("não alvo", text)
        self.assertIn("Suporte por reads não foi medido", text)
        self.assertIn("atribuição taxonômica", text)

    def test_control_not_applicable_does_not_release_detected_or_actionable(self):
        value = classify(
            "control", [_panel_locus()], [], [], [], "CONTROL_NOT_APPLICABLE", "shotgun",
        )
        self.assertEqual(value["evidence_level"], "REVIEW")
        self.assertNotEqual(value["analysis_outcome"], "EVIDENCE_RECOVERED")
        self.assertNotIn("DETECTED", json.dumps(value))
        self.assertEqual(
            confidence_tier_for("STRONG", control_status="CONTROL_NOT_APPLICABLE"),
            "REVIEW",
        )

    def test_only_short_builder_evidence_stays_review_in_a_validated_batch(self):
        fragments = [{"qseqid": "q", "qlen": "80", "assembly_method": "builder"}]
        value = classify(
            "sample", [_panel_locus()], [], [], [], "CONTROL_BELOW_SAMPLE", "shotgun",
            fragments=fragments,
        )
        self.assertEqual(value["evidence_level"], "REVIEW")
        self.assertEqual(value["analysis_outcome"], "CANDIDATES_FOR_REVIEW")
        self.assertIn("fragmento curto do Builder", "\n".join(value["caveats"]))
        longer = [{"qseqid": "q", "qlen": "240", "assembly_method": "builder"}]
        kept = classify(
            "sample", [_panel_locus()], [], [], [], "CONTROL_BELOW_SAMPLE", "shotgun",
            fragments=longer,
        )
        self.assertEqual(kept["evidence_level"], "DETECTED")

    def test_report_follows_control_status_and_evidence_label(self):
        import subprocess
        script = ROOT / "scripts/pipeline/report_minimal.sh"
        sequence = "ACGT" * 25
        blast = "\t".join([
            "NODE1", "ref1", "95.0", "90", "1", "0", "1", "90", "1", "90",
            "1e-20", "200", "100", "100", "85", "0",
        ]) + "\n"

        def run(extra):
            directory = Path(tempfile.mkdtemp())
            contigs = directory / "contigs.fa"
            contigs.write_text(f">NODE1\n{sequence}\n", encoding="utf-8")
            table = directory / "hits.tsv"
            table.write_text(blast, encoding="utf-8")
            out = directory / "reports" / "amostra_summary.md"
            out.parent.mkdir()
            completed = subprocess.run(
                ["bash", str(script), "--sample", "amostra", "--contigs", str(contigs),
                 "--blast", str(table), "--out", str(out), *extra],
                capture_output=True, text=True, check=False,
            )
            summary = (directory / "blast" / "amostra_hit_contigs_summary.tsv").read_text(encoding="utf-8")
            return completed, out.read_text(encoding="utf-8"), summary

        validated, validated_md, validated_summary = run(["--control-status", "CONTROL_BELOW_SAMPLE"])
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertIn("ACTIONABLE", validated_summary)
        self.assertIn("CONTROL_BELOW_SAMPLE", validated_md)
        self.assertNotIn("sem controle validado", validated_md)
        plain, plain_md, plain_summary = run(["--control-status", "UNCONTROLLED"])
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertNotIn("ACTIONABLE", plain_summary.splitlines()[1])
        self.assertIn("REVIEW", plain_summary)
        self.assertNotIn("sem controle validado", plain_md)
        capped, capped_md, capped_summary = run([
            "--control-status", "CONTROL_BELOW_SAMPLE", "--evidence-level", "REVIEW",
        ])
        self.assertEqual(capped.returncode, 0, capped.stderr)
        self.assertIn("REVIEW (estado CONTROL_BELOW_SAMPLE)", capped_md)
        self.assertNotIn("ACTIONABLE", capped_summary.splitlines()[1])
        self.assertNotIn("sem controle validado", capped_md)


if __name__ == "__main__":
    unittest.main()
