import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from classify_sample import classify
from evidence_contract import validate_document
from export_evidence import render
from summarize_coverage import summarize


class SampleClassTests(unittest.TestCase):
    def test_coverage_metrics_separate_whole_genome_and_covered_positions(self):
        loci = [{"sseqid": "ref", "category": "TARGET_VIRUS", "locus_id": "L1", "orientation": "+", "query_ids": "q", "reference_intervals": "1-10"}]
        row = summarize({"ref": {1: 3, 2: 3}}, {"ref": 10}, loci, 2, 10, 20)[0]
        self.assertEqual(float(row["breadth_1x"]), 0.2)
        self.assertEqual(float(row["breadth_3x"]), 0.2)
        self.assertEqual(float(row["median_depth_covered"]), 3.0)
        self.assertEqual(float(row["mean_depth_locus"]), 0.6)



    def test_measured_zero_coverage_remains_available_low_coverage(self):
        locus = {
            "locus_id": "L1", "sseqid": "virus", "query_ids": "q1",
            "orientation": "+", "task": "blastn", "category": "TARGET_VIRUS",
            "covered_reference_bp": "80", "max_query_length": "80",
        }
        competitive = [{
            "qseqid": "q1", "task": "blastn", "specificity_status": "TARGET_SPECIFIC",
        }]
        support = [{
            "reference_id": "virus", "category": "TARGET_VIRUS", "locus_id": "L1",
            "unique_templates": "3", "distinct_starts": "2",
            "proper_pair_templates": "3", "support_status": "SUPPORT_AVAILABLE",
        }]
        coverage = [{
            "reference_id": "virus", "category": "TARGET_VIRUS", "locus_id": "L1",
            "breadth_1x": "0", "breadth_3x": "0", "median_depth_covered": "0",
            "max_window_depth_fraction": "0",
        }]
        result = classify(
            "synthetic", [locus], competitive, support, coverage,
            "UNCONTROLLED", "shotgun", False,
        )
        self.assertEqual(result["candidates"][0]["coverage"]["status"], "AVAILABLE")
        self.assertEqual(result["coverage_status"], "INSUFFICIENT_COVERAGE")
        self.assertEqual(result["metrics"]["breadth_1x"], 0.0)

    def test_unmeasured_candidate_metrics_cannot_carry_numeric_signal(self):
        result = classify(
            "synthetic",
            [{
                "locus_id": "L1", "sseqid": "virus", "query_ids": "q1",
                "orientation": "+", "task": "blastn", "category": "TARGET_VIRUS",
                "covered_reference_bp": "40", "max_query_length": "40",
            }],
            [{"qseqid": "q1", "task": "blastn", "specificity_status": "TARGET_SPECIFIC"}],
            [], [], "UNCONTROLLED", "shotgun", False,
        )
        result["candidates"][0]["support"]["unique_templates"] = 1
        with self.assertRaisesRegex(ValueError, "must be zero when support is not measured"):
            validate_document(result)

        result["candidates"][0]["support"]["unique_templates"] = 0
        result["candidates"][0]["coverage"]["breadth_1x"] = 0.01
        with self.assertRaisesRegex(ValueError, "must be zero when coverage is not measured"):
            validate_document(result)

    def test_candidate_orientation_is_required_and_both_strands_are_representable(self):
        candidates = []
        for index, orientation in enumerate(("+", "-"), 1):
            locus = {
                "locus_id": f"L{index}", "sseqid": "virus", "query_ids": f"q{index}",
                "orientation": orientation, "task": "blastn", "category": "TARGET_VIRUS",
                "covered_reference_bp": "40", "max_query_length": "40",
            }
            competitive = {
                "qseqid": f"q{index}", "task": "blastn", "specificity_status": "TARGET_SPECIFIC",
            }
            result = classify(
                "synthetic", [locus], [competitive], [], [], "UNCONTROLLED", "shotgun", False,
            )
            candidates.append(result["candidates"][0])
        self.assertEqual([candidate["orientation"] for candidate in candidates], ["+", "-"])

        document = classify(
            "synthetic",
            [{
                "locus_id": "L3", "sseqid": "virus", "query_ids": "q3", "orientation": "+",
                "task": "blastn", "category": "TARGET_VIRUS", "covered_reference_bp": "40",
                "max_query_length": "40",
            }],
            [{"qseqid": "q3", "task": "blastn", "specificity_status": "TARGET_SPECIFIC"}],
            [], [], "UNCONTROLLED", "shotgun", False,
        )
        document["candidates"][0].pop("orientation")
        with self.assertRaisesRegex(ValueError, "candidate missing fields: orientation"):
            validate_document(document)


if __name__ == "__main__":
    unittest.main()
