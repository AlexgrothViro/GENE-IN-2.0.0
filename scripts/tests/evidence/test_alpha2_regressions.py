import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from blast_router import profiles_for_length
from activation_policy import POLICY_IDENTITY_FIELDS, load_public_activation_policy, policy_identity
from classify_sample import classify
from common import build_artifact_manifest, read_tsv, validate_artifact_manifest, write_json_atomic
from evaluate_controls import evaluate
from evidence_contract import (
    not_evaluable_document, promote_for_public_output, validate_document,
)
from finalize_batch import validate_batch_evidence
from phylogeny_gate import candidate_scoped_information
from summarize_read_support import summarize_sam


BLAST_CONFIG = {
    "blast": {"short_max_bp": 29, "dual_mode_min_bp": 30, "dual_mode_max_bp": 49,
              "explicit_dust": True, "soft_masking": True}
}


def locus(locus_id="L1", reference="virus", query="q"):
    return {
        "locus_id": locus_id, "sseqid": reference, "category": "TARGET_VIRUS",
        "query_ids": query, "orientation": "+", "task": "blastn",
        "covered_reference_bp": "80", "reference_intervals": "1-80",
    }


def competitive(query="q"):
    return {"qseqid": query, "task": "blastn", "specificity_status": "TARGET_SPECIFIC"}


class Alpha2RegressionTests(unittest.TestCase):
    def test_host_support_is_not_attributed_to_target(self):
        support = [{
            "reference_id": "HOST_chr1", "category": "HOST_REFERENCE", "locus_id": "HOST_L1",
            "support_status": "SUPPORT_AVAILABLE", "unique_templates": "100", "distinct_starts": "100",
        }]
        coverage = [{
            "reference_id": "HOST_chr1", "category": "HOST_REFERENCE", "locus_id": "HOST_L1",
            "breadth_1x": "1", "breadth_3x": "1", "median_depth_covered": "100",
        }]
        value = classify("sample", [locus()], [competitive()], support, coverage,
                         "CONTROL_BELOW_SAMPLE", "shotgun")
        self.assertEqual(value["evidence_level"], "DETECTED")
        self.assertEqual(value["candidates"][0]["support"]["status"], "NOT_EVALUATED")
        self.assertEqual(value["candidates"][0]["coverage"]["status"], "NOT_EVALUATED")

    def test_support_must_match_reference_category_and_locus(self):
        wrong_locus = [{
            "reference_id": "virus", "category": "TARGET_VIRUS", "locus_id": "L2",
            "support_status": "SUPPORT_AVAILABLE", "unique_templates": "9", "distinct_starts": "9",
        }]
        value = classify("sample", [locus("L1")], [competitive()], wrong_locus, [],
                         "CONTROL_BELOW_SAMPLE", "shotgun")
        self.assertEqual(value["candidates"][0]["support"]["status"], "NOT_EVALUATED")
        self.assertEqual(value["metrics"]["unique_templates"], 0)

    def test_reference_only_variation_is_not_candidate_information(self):
        query = "----AAAA"
        refs = ["ACGTAAAA", "ACGTAAAA", "TGCAAAAA", "TGCAAAAA"]
        metrics = candidate_scoped_information(query, refs)
        self.assertEqual(metrics["candidate_covered_columns"], 4)
        self.assertEqual(metrics["informative_sites_within_candidate_span"], 0)

    def test_informative_sites_are_limited_to_candidate_span(self):
        query = "----AAAA"
        refs = ["ACGTAAAA", "ACGTAAAA", "TGCAAAAA", "TGCAAAAA"]
        metrics = candidate_scoped_information(query, refs)
        self.assertEqual(metrics["candidate_covered_columns"], 4)
        self.assertLessEqual(metrics["informative_sites_within_candidate_span"], 4)

    def test_zero_filtered_hits_is_no_evidence_not_absence(self):
        value = classify("sample", [], [], [], [], "UNCONTROLLED", "unknown")
        self.assertEqual(value["execution_status"], "done")
        self.assertEqual(value["analysis_outcome"], "NO_EVIDENCE_RECOVERED")
        self.assertEqual(value["evidence_level"], "NO_SIGNAL")
        self.assertEqual(value["candidates"], [])
        self.assertTrue(any("não demonstra ausência" in item for item in value["caveats"]))

    def test_failed_scientific_stage_is_not_evaluable(self):
        value = not_evaluable_document("sample", "run-failed", "artefato científico inválido")
        self.assertEqual(value["analysis_outcome"], "NOT_EVALUABLE")
        self.assertEqual(value["evidence_level"], "NOT_EVALUABLE")
        self.assertEqual(value["execution_status"], "failed")

    def test_failed_execution_cannot_masquerade_as_no_evidence(self):
        value = classify("sample", [], [], [], [], "UNCONTROLLED", "unknown")
        value["execution_status"] = "failed"
        with self.assertRaisesRegex(ValueError, "requires NOT_EVALUABLE"):
            validate_document(value)

    def test_nonterminal_execution_cannot_be_promoted_as_evidence(self):
        value = classify("sample", [], [], [], [], "UNCONTROLLED", "unknown")
        value["execution_status"] = "running"
        with self.assertRaisesRegex(ValueError, "terminal execution_status"):
            validate_document(value)

    def test_e4_is_never_a_software_output(self):
        value = classify("sample", [], [], [], [], "UNCONTROLLED", "unknown")
        value["evidence_level"] = "E4"
        with self.assertRaisesRegex(ValueError, "invalid evidence_level"):
            validate_document(value)



    def test_invalid_utf8_blocks_scientific_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.tsv"
            path.write_bytes(b"a\tb\n1\t\xff\n")
            with self.assertRaises(UnicodeDecodeError):
                read_tsv(path)

    def test_malformed_sam_blocks_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.sam"
            path.write_text("read\t0\tref\t1\t60\t10M\t*\t0\t0\tACGT\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"bad\.sam:1"):
                summarize_sam(str(path), "sample", "shotgun", "none", 10)

    def test_umi_dedup_is_reproducible_with_seed(self):
        script = (ROOT / "scripts" / "evidence" / "map_read_support.sh").read_text(encoding="utf-8")
        self.assertIn('--random-seed "$UMI_SEED"', script)
        sam = "pair\t0\tref\t1\t60\t10M\t*\t0\t0\tACGT\tIIII\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reads.sam"; path.write_text(sam, encoding="utf-8")
            first = summarize_sam(str(path), "sample", "shotgun", "none", 10)
            second = summarize_sam(str(path), "sample", "shotgun", "none", 10)
        self.assertEqual(first, second)

    def test_length_routes_to_expected_blast_profile(self):
        self.assertEqual(profiles_for_length(20, BLAST_CONFIG), ("short",))
        self.assertEqual(profiles_for_length(30, BLAST_CONFIG), ("short", "conventional"))
        self.assertEqual(profiles_for_length(80, BLAST_CONFIG), ("conventional",))


    def test_negative_donor_receiver_pattern_is_reported(self):
        manifest = [
            {"batch_id": "b", "sample_id": "donor", "role": "sample", "library_mode": "shotgun", "umi_mode": "none", "r1": "a", "r2": "b", "expected_target": "virus"},
            {"batch_id": "b", "sample_id": "receiver", "role": "sample", "library_mode": "shotgun", "umi_mode": "none", "r1": "c", "r2": "d", "expected_target": "virus"},
        ]
        metrics = [
            {"batch_id": "b", "sample_id": "donor", "target": "virus", "rpm_post_qc": "100", "rpm_nonhost": "NA", "sequence_hashes": "same", "analysis_outcome": "EVIDENCE_RECOVERED"},
            {"batch_id": "b", "sample_id": "receiver", "target": "virus", "rpm_post_qc": "1", "rpm_nonhost": "NA", "sequence_hashes": "same", "analysis_outcome": "EVIDENCE_RECOVERED"},
        ]
        by_sample = {row["sample_id"]: row for row in evaluate(manifest, metrics, 10)}
        self.assertEqual(by_sample["receiver"]["control_status"], "INDEX_HOPPING_SUSPECTED")
        self.assertEqual(by_sample["receiver"]["donor_sample_id"], "donor")

    def test_success_requires_complete_verified_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "sample_evidence.json"
            write_json_atomic(artifact, not_evaluable_document("sample", "run", "falha controlada"))
            manifest = build_artifact_manifest(root)
            self.assertEqual(validate_artifact_manifest(root, manifest), [])
            artifact.write_text("{}\n", encoding="utf-8")
            self.assertTrue(validate_artifact_manifest(root, manifest))



if __name__ == "__main__":
    unittest.main()
