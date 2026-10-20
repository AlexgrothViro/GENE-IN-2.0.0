import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from evaluate_controls import evaluate
from collect_batch_metrics import positive_control_qualification
from classify_sample import classify


class ControlTests(unittest.TestCase):
    def test_tenfold_ratio_is_state_not_contamination_verdict(self):
        manifest = [
            {"batch_id": "b", "sample_id": "s", "role": "sample", "library_mode": "shotgun", "umi_mode": "none", "r1": "a", "r2": "b", "expected_target": "virus"},
            {"batch_id": "b", "sample_id": "n", "role": "negative_library", "library_mode": "shotgun", "umi_mode": "none", "r1": "c", "r2": "d", "expected_target": "virus"},
        ]
        metrics = [
            {"batch_id": "b", "sample_id": "s", "target": "virus", "rpm_post_qc": "100", "rpm_nonhost": "NA", "sequence_hashes": "x"},
            {"batch_id": "b", "sample_id": "n", "target": "virus", "rpm_post_qc": "5", "rpm_nonhost": "NA", "sequence_hashes": "y"},
        ]
        row = evaluate(manifest, metrics, 10)[0]
        self.assertEqual(row["control_status"], "CONTROL_BELOW_SAMPLE")
        self.assertNotIn("CONTAMINATION", row["control_status"])

    def test_failed_positive_is_target_failure_and_control_is_not_applicable(self):
        manifest = [
            {"batch_id": "b", "sample_id": "s", "role": "sample", "library_mode": "shotgun", "umi_mode": "none", "r1": "a", "r2": "b", "expected_target": "virus"},
            {"batch_id": "b", "sample_id": "p", "role": "positive", "library_mode": "shotgun", "umi_mode": "none", "r1": "c", "r2": "d", "expected_target": "virus"},
        ]
        metrics = [
            {"batch_id": "b", "sample_id": "s", "target": "virus", "rpm_post_qc": "100", "rpm_nonhost": "NA", "sequence_hashes": "x", "evidence_level": "LOCUS_CANDIDATE"},
            {"batch_id": "b", "sample_id": "p", "target": "virus", "expected_target": "virus", "rpm_post_qc": "0", "rpm_nonhost": "NA", "sequence_hashes": "", "evidence_level": "INCONCLUSIVE"},
        ]
        rows = evaluate(manifest, metrics, 10)
        by_sample = {row["sample_id"]: row for row in rows}
        self.assertEqual(by_sample["s"]["control_status"], "TARGET_CONTROL_FAILURE")
        self.assertEqual(by_sample["p"]["control_status"], "CONTROL_NOT_APPLICABLE")
    def test_explicit_not_qualified_positive_is_reported(self):
        manifest = [
            {"batch_id": "b", "sample_id": "s", "role": "sample", "library_mode": "shotgun", "umi_mode": "none", "r1": "a", "r2": "b", "expected_target": "virus"},
            {"batch_id": "b", "sample_id": "p", "role": "positive", "library_mode": "shotgun", "umi_mode": "none", "r1": "c", "r2": "d", "expected_target": "virus"},
        ]
        metrics = [
            {"batch_id": "b", "sample_id": "s", "target": "virus", "rpm_post_qc": "10", "rpm_nonhost": "NA", "sequence_hashes": "x", "analysis_outcome": "EVIDENCE_RECOVERED", "positive_control_qualification": "NOT_QUALIFIED"},
            {"batch_id": "b", "sample_id": "p", "target": "virus", "expected_target": "virus", "rpm_post_qc": "1", "rpm_nonhost": "NA", "sequence_hashes": "y", "analysis_outcome": "EVIDENCE_RECOVERED", "positive_control_qualification": "NOT_QUALIFIED"},
        ]
        by_sample = {row["sample_id"]: row for row in evaluate(manifest, metrics, 10)}
        self.assertEqual(by_sample["s"]["control_status"], "TARGET_CONTROL_FAILURE")

    def test_explicitly_qualified_positive_control_allows_control_evaluation(self):
        manifest = [
            {"batch_id": "b", "sample_id": "s", "role": "sample", "library_mode": "shotgun", "umi_mode": "none", "r1": "a", "r2": "b", "expected_target": "virus"},
            {"batch_id": "b", "sample_id": "p", "role": "positive", "library_mode": "shotgun", "umi_mode": "none", "r1": "c", "r2": "d", "expected_target": "virus"},
        ]
        metrics = [
            {"batch_id": "b", "sample_id": "s", "target": "virus", "rpm_post_qc": "10", "rpm_nonhost": "NA", "sequence_hashes": "x", "positive_control_qualification": "NOT_QUALIFIED"},
            {"batch_id": "b", "sample_id": "p", "target": "virus", "expected_target": "virus", "rpm_post_qc": "10", "rpm_nonhost": "NA", "sequence_hashes": "y", "positive_control_qualification": "QUALIFIED"},
        ]
        by_sample = {row["sample_id"]: row for row in evaluate(manifest, metrics, 10)}
        self.assertEqual(by_sample["s"]["control_status"], "UNCONTROLLED")


    def test_failed_positives_do_not_invalidate_an_unrelated_batch(self):
        manifest = [
            {"batch_id": "bad", "sample_id": "p1", "role": "positive", "library_mode": "shotgun", "umi_mode": "none", "r1": "a", "r2": "b", "expected_target": "v1"},
            {"batch_id": "bad", "sample_id": "p2", "role": "positive", "library_mode": "shotgun", "umi_mode": "none", "r1": "c", "r2": "d", "expected_target": "v2"},
            {"batch_id": "good", "sample_id": "s", "role": "sample", "library_mode": "shotgun", "umi_mode": "none", "r1": "e", "r2": "f", "expected_target": "v3"},
        ]
        metrics = [
            {"batch_id": "bad", "sample_id": "p1", "target": "v1", "expected_target": "v1", "rpm_post_qc": "0", "rpm_nonhost": "NA", "sequence_hashes": "", "positive_control_qualification": "NOT_QUALIFIED"},
            {"batch_id": "bad", "sample_id": "p2", "target": "v2", "expected_target": "v2", "rpm_post_qc": "0", "rpm_nonhost": "NA", "sequence_hashes": "", "positive_control_qualification": "NOT_QUALIFIED"},
            {"batch_id": "good", "sample_id": "s", "target": "v3", "rpm_post_qc": "1", "rpm_nonhost": "NA", "sequence_hashes": "x", "positive_control_qualification": "NOT_QUALIFIED"},
        ]
        by_sample = {row["sample_id"]: row for row in evaluate(manifest, metrics, 10)}
        self.assertEqual(by_sample["s"]["control_status"], "UNCONTROLLED")


if __name__ == "__main__":
    unittest.main()
