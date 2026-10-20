import hashlib
import json
import platform
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))

from evidence_analytics import EvidenceAnalyticsService  # noqa: E402
from evidence_dashboard import EvidenceDashboardService  # noqa: E402
from classify_sample import classify
from activation_policy import load_activation_policy  # noqa: E402


class EvidenceAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        fixture = ROOT / "scripts" / "tests" / "evidence" / "fixtures" / "alpha2_complete"
        self.run_id = "fixture-alpha2-run"
        self.run_dir = self.root / "results" / "evidence" / "runs" / self.run_id
        shutil.copytree(fixture, self.run_dir)
        config_dir = self.root / "config"
        config_dir.mkdir()
        for name in ("evidence_profiles.json", "evidence_activation.json"):
            shutil.copy2(ROOT / "config" / name, config_dir / name)
        policy = load_activation_policy(config_dir / "evidence_activation.json")
        # inspect_run() also compares scientific_role/shadow_mode/evidence_ceiling
        # against the active policy, not only the 5 identity fields.
        identity_fields = (
            "profile_id", "profile_version", "profile_sha256",
            "activation_record_id", "activation_record_sha256",
            "scientific_role", "shadow_mode", "evidence_ceiling",
        )
        identity = {field: policy[field] for field in identity_fields}
        profiles = config_dir / "evidence_profiles.json"
        provenance = {
            "fixture": True,
            "schema_version": "2.0",
            "pipeline_version": "2.0.0-alpha.2",
            "platform": platform.platform(),
            "config_path": str(profiles.resolve()),
            "config_sha256": hashlib.sha256(profiles.read_bytes()).hexdigest(),
            "parameters": {"fixture": "analytics"},
            "artifacts": {"evidence_profiles": {
                "path": str(profiles.resolve()),
                "size": profiles.stat().st_size,
                "sha256": hashlib.sha256(profiles.read_bytes()).hexdigest(),
            }},
            "tools": {"python3": {
                "version": sys.version.splitlines()[0],
                "executable": str(Path(sys.executable).resolve()),
                "sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            }},
        }
        for name in ("sample_evidence.json", "run_state.json"):
            path = self.run_dir / name
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.update(identity)
            if name == "sample_evidence.json":
                payload = classify("fixture-alpha2", [], [], [], [], "UNCONTROLLED", "unknown", provenance=provenance, run_id=self.run_id)
            else:
                payload.update({"shadow_mode": False, "evidence_level": "NO_SIGNAL", "reported_conclusion": "NO_EVIDENCE_RECOVERED"})
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        self.run_dir.joinpath("provenance.json").write_text(
            json.dumps(provenance, sort_keys=True), encoding="utf-8",
        )
        success_path = self.run_dir / "SUCCESS.json"
        success = json.loads(success_path.read_text(encoding="utf-8"))
        success.update(identity)
        success_path.write_text(json.dumps(success, sort_keys=True), encoding="utf-8")
        state_dir = self.root / "results" / "evidence" / "state"
        state_dir.mkdir(parents=True)
        shutil.copy2(self.run_dir / "run_state.json", state_dir / f"{self.run_id}.json")
        self._refresh_manifest_hashes_for(self.run_dir, "sample_evidence.json")
        self._refresh_manifest_hashes_for(self.run_dir, "run_state.json")
        self._refresh_manifest_hashes_for(self.run_dir, "provenance.json")
        self.evidence = EvidenceDashboardService(self.root)
        self.analytics = EvidenceAnalyticsService(self.evidence)
        self.addCleanup(self._tmp.cleanup)

    def test_summary_uses_validated_promoted_artifacts(self):
        payload = self.analytics.summary(self.run_id)
        self.assertTrue(payload["validation"]["valid"])
        self.assertEqual(payload["metadata"]["sample_id"], "fixture-alpha2")
        self.assertEqual(payload["metadata"]["pipeline_version"], "2.0.0-alpha.2")
        self.assertEqual(payload["metadata"]["analysis_outcome"], "NO_EVIDENCE_RECOVERED")
        self.assertEqual(payload["metadata"]["reported_conclusion"], "NO_EVIDENCE_RECOVERED")
        self.assertEqual(payload["controls"]["status"], "UNCONTROLLED")
        self.assertIn("não possui controles associados", payload["controls"]["explanation"])
        self.assertEqual(payload["metadata"]["promotion_status"], "NONE")
        self.assertTrue(any("não demonstra ausência" in item for item in payload["caveats"]))
        self.assertTrue(payload["provenance"]["fixture"])
        self.assertEqual(payload["candidates"], [])
        self.assertEqual(payload["promotion_summary"], {"total": 0, "eligible": 0, "blocked": 0, "status": "NONE"})
        self.assertEqual(payload["datasets"]["coverage"]["status"], "not_measured")
        self.assertIsNone(payload["datasets"]["coverage"]["rows"])
        self.assertEqual(len(payload["gates"]), 0)
        self.assertEqual(len(payload["stages"]), 12)

    def test_dataset_paginates_and_filters_without_silent_sampling(self):
        path = self.run_dir / "read_support.tsv"
        header = path.read_text(encoding="utf-8").splitlines()[0]
        rows = [
            f"sample\tref-{index % 2}\tviral\tlocus-{index % 3}\t+\tq{index}\tshotgun\tnone\tSUPPORTED\t{index}\t1\t0\t0\t20"
            for index in range(12)
        ]
        path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        self._refresh_manifest_hashes("read_support.tsv")

        payload = self.analytics.dataset(
            self.run_id, "read_support", reference_id="ref-1", offset=1, limit=2
        )
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["total"], 6)
        self.assertEqual(len(payload["rows"]), 2)
        self.assertTrue(payload["truncated"])
        self.assertTrue(all(row["reference_id"] == "ref-1" for row in payload["rows"]))

    def test_dataset_and_pagination_are_allowlisted(self):
        with self.assertRaises(ValueError):
            self.analytics.dataset(self.run_id, "../../SUCCESS.json")
        with self.assertRaises(ValueError):
            self.analytics.dataset(self.run_id, "coverage", limit=501)
        with self.assertRaises(ValueError):
            self.analytics.dataset("../escape", "coverage")

    def test_invalid_artifact_is_explicit_and_never_becomes_zero(self):
        (self.run_dir / "SUCCESS.json").write_text("not-json\n", encoding="utf-8")
        payload = self.analytics.summary(self.run_id)
        self.assertFalse(payload["validation"]["valid"])
        self.assertIsNone(payload["metrics"])
        self.assertIsNone(payload["metadata"]["reported_conclusion"])
        self.assertEqual(payload["metadata"]["analysis_outcome"], "NOT_EVALUABLE")
        self.assertEqual(payload["metadata"]["evidence_level"], "NOT_EVALUABLE")
        self.assertIsNone(payload["controls"]["status"])
        self.assertEqual(payload["caveats"], [])
        self.assertIsNone(payload["provenance"])
        self.assertEqual(payload["candidates"], [])
        self.assertIsNone(payload["datasets"]["read_support"]["rows"])
        self.assertEqual(payload["datasets"]["read_support"]["status"], "invalid")

    def test_optional_missing_and_empty_datasets_remain_distinct(self):
        before = self.analytics.summary(self.run_id)
        self.assertEqual(before["datasets"]["read_support"]["status"], "empty")
        self.assertEqual(before["datasets"]["read_support"]["rows"], 0)
        manifest_path = self.run_dir / "artifact_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].pop("template_lineage.tsv")
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        (self.run_dir / "template_lineage.tsv").unlink()
        success_path = self.run_dir / "SUCCESS.json"
        success = json.loads(success_path.read_text(encoding="utf-8"))
        success["artifact_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        success["artifact_count"] -= 1
        success_path.write_text(json.dumps(success), encoding="utf-8")

        payload = self.analytics.summary(self.run_id)
        self.assertFalse(payload["validation"]["valid"])
        self.assertEqual(payload["datasets"]["template_lineage"]["status"], "missing")
        self.assertIsNone(payload["datasets"]["template_lineage"]["rows"])
        self.assertEqual(payload["datasets"]["read_support"]["status"], "invalid")
        self.assertIsNone(payload["datasets"]["read_support"]["rows"])

    def test_compare_accepts_two_to_four_and_blocks_incompatible_overlay(self):
        second = "fixture-alpha2-second"
        second_dir = self.root / "results" / "evidence" / "runs" / second
        shutil.copytree(self.run_dir, second_dir)
        state = json.loads((second_dir / "run_state.json").read_text(encoding="utf-8"))
        state["run_id"] = second
        state["policy_version"] = "different-policy"
        state_path = self.root / "results" / "evidence" / "state" / f"{second}.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        evidence = json.loads((second_dir / "sample_evidence.json").read_text(encoding="utf-8"))
        evidence["run_id"] = second
        second_dir.joinpath("sample_evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
        success = json.loads((second_dir / "SUCCESS.json").read_text(encoding="utf-8"))
        success["run_id"] = second
        success["policy_version"] = "different-policy"
        second_dir.joinpath("SUCCESS.json").write_text(json.dumps(success), encoding="utf-8")
        self._refresh_manifest_hashes_for(second_dir, "sample_evidence.json")

        payload = self.analytics.compare([self.run_id, second])
        self.assertFalse(payload["compatibility"]["overlay_allowed"])
        self.assertIn("policy_version", [item["field"] for item in payload["compatibility"]["conflicts"]])
        with self.assertRaises(ValueError):
            self.analytics.compare([self.run_id])
        with self.assertRaises(ValueError):
            self.analytics.compare([self.run_id] * 5)

    def _refresh_manifest_hashes(self, filename):
        self._refresh_manifest_hashes_for(self.run_dir, filename)

    @staticmethod
    def _refresh_manifest_hashes_for(run_dir, filename):
        manifest_path = run_dir / "artifact_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        target = run_dir / filename
        manifest["files"][filename] = {
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "size": target.stat().st_size,
        }
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        success_path = run_dir / "SUCCESS.json"
        success = json.loads(success_path.read_text(encoding="utf-8"))
        success["artifact_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if filename == "sample_evidence.json":
            success["sample_evidence_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        success_path.write_text(json.dumps(success), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
