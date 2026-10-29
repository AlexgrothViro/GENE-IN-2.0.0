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
from export_candidate_sequences import _summary_rows
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
        value = classify("sample", [_locus()], [], [], [], "UNCONTROLLED", "shotgun")
        self.assertEqual(value["analysis_outcome"], "CANDIDATES_FOR_REVIEW")
        self.assertEqual(value["evidence_level"], "REVIEW")
        self.assertNotIn("DETECTED", json.dumps(value))
        self.assertNotIn("ACTIONABLE", json.dumps(value))

    def test_validated_control_can_carry_detected(self):
        value = classify(
            "sample", [_locus()], [], [], [], "CONTROL_BELOW_SAMPLE", "shotgun",
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


if __name__ == "__main__":
    unittest.main()
