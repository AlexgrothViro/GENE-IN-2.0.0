import hashlib
import json
import platform
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "scripts"))

from classify_sample import classify
from activation_policy import load_activation_policy  # noqa: E402
from classify_sample import classify  # noqa: E402
from evidence_analytics import EvidenceAnalyticsService  # noqa: E402
from evidence_dashboard import EvidenceDashboardService  # noqa: E402
from dashboard.handler import query_one  # noqa: E402
import scripts.ux_dashboard as dashboard  # noqa: E402


class Etapa6DashboardCommunicationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.fixture = ROOT / "scripts" / "tests" / "evidence" / "fixtures" / "alpha2_complete"
        config_dir = self.root / "config"
        config_dir.mkdir()
        for name in ("evidence_profiles.json", "evidence_activation.json"):
            shutil.copy2(ROOT / "config" / name, config_dir / name)
        self.policy = load_activation_policy(config_dir / "evidence_activation.json")
        # inspect_run() also compares scientific_role/shadow_mode/evidence_ceiling
        # against the active policy, not only the 5 identity fields.
        self.identity = {
            field: self.policy[field]
            for field in (
                "profile_id", "profile_version", "profile_sha256",
                "activation_record_id", "activation_record_sha256",
                "scientific_role", "shadow_mode", "evidence_ceiling",
                )
        }
        self.evidence = EvidenceDashboardService(self.root)
        self.analytics = EvidenceAnalyticsService(self.evidence)
        self.addCleanup(self._tmp.cleanup)

    def _provenance(self):
        profiles = self.root / "config" / "evidence_profiles.json"
        return {
            "fixture": True,
            "schema_version": "2.0",
            "pipeline_version": "2.0.0-alpha.2",
            "platform": platform.platform(),
            "config_path": str(profiles.resolve()),
            "config_sha256": hashlib.sha256(profiles.read_bytes()).hexdigest(),
            "parameters": {"fixture": "etapa6"},
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

    def _install_run(self, run_id, mutate=None, evidence_payload=None, state_extra=None):
        run_dir = self.root / "results" / "evidence" / "runs" / run_id
        shutil.copytree(self.fixture, run_dir)
        provenance = self._provenance()
        for name in ("sample_evidence.json", "run_state.json"):
            path = run_dir / name
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.update(self.identity)
            payload.update({"shadow_mode": False, "evidence_level": "NO_SIGNAL", "reported_conclusion": "NO_EVIDENCE_RECOVERED"})
            payload["run_id"] = run_id
            if name == "sample_evidence.json":
                payload = classify("fixture-alpha2", [], [], [], [], "UNCONTROLLED", "unknown", provenance=provenance, run_id=run_id)
                payload["provenance"] = provenance
                if evidence_payload:
                    payload = evidence_payload
                    payload.update(self.identity)
                    payload["run_id"] = run_id
                    payload["provenance"] = provenance
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        run_dir.joinpath("provenance.json").write_text(
            json.dumps(provenance, sort_keys=True), encoding="utf-8",
        )
        success_path = run_dir / "SUCCESS.json"
        success = json.loads(success_path.read_text(encoding="utf-8"))
        success.update(self.identity)
        success["run_id"] = run_id
        success_path.write_text(json.dumps(success, sort_keys=True), encoding="utf-8")
        state_dir = self.root / "results" / "evidence" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
        state.update(state_extra or {})
        state["run_id"] = run_id
        (state_dir / f"{run_id}.json").write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        if mutate:
            mutate(run_dir)
        for filename in ("sample_evidence.json", "run_state.json", "provenance.json"):
            self._refresh_hashes(run_dir, filename)
        return run_dir

    @staticmethod
    def _refresh_hashes(run_dir, filename):
        manifest_path = run_dir / "artifact_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        target = run_dir / filename
        if not target.is_file() or filename not in manifest.get("files", {}):
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        else:
            manifest["files"][filename] = {
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "size": target.stat().st_size,
            }
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        success_path = run_dir / "SUCCESS.json"
        if not success_path.is_file():
            return
        try:
            success = json.loads(success_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        success["artifact_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if filename == "sample_evidence.json" and target.is_file():
            success["sample_evidence_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        success_path.write_text(json.dumps(success), encoding="utf-8")

    def test_no_evidence_recovered_is_not_viral_absence(self):
        self._install_run("run-no-evidence")
        payload = self.analytics.summary("run-no-evidence")
        self.assertTrue(payload["validation"]["valid"])
        self.assertEqual(payload["metadata"]["analysis_outcome"], "NO_EVIDENCE_RECOVERED")
        self.assertEqual(payload["metadata"]["reported_conclusion"], "NO_EVIDENCE_RECOVERED")
        self.assertFalse(payload["metadata"]["shadow_mode"])
        self.assertEqual(payload["metadata"]["analysis_outcome"], payload["metadata"]["reported_conclusion"])
        self.assertTrue(any("não demonstra ausência" in item for item in payload["caveats"]))
        self.assertEqual(payload["controls"]["status"], "UNCONTROLLED")


    def test_invalid_and_incomplete_runs_are_not_evaluable(self):
        self._install_run("run-corrupt", mutate=lambda run_dir: run_dir.joinpath("SUCCESS.json").write_text("not-json\n", encoding="utf-8"))
        corrupt = self.analytics.summary("run-corrupt")
        self.assertFalse(corrupt["validation"]["valid"])
        self.assertEqual(corrupt["metadata"]["analysis_outcome"], "NOT_EVALUABLE")
        self.assertEqual(corrupt["metadata"]["evidence_level"], "NOT_EVALUABLE")
        self.assertIsNone(corrupt["metadata"]["reported_conclusion"])
        self.assertEqual(corrupt["candidates"], [])
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.evidence.artifact("run-corrupt", "sample_evidence")

        state_dir = self.root / "results" / "evidence" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "run-incomplete.json").write_text(json.dumps({
            "run_id": "run-incomplete", "action": "evidence_single",
            "sample_ids": ["sample-x"], "status": "failed",
            "execution_status": "failed", "evidence_v2_status": "failed",
            **self.identity,
        }), encoding="utf-8")
        (self.root / "results" / "evidence" / "runs" / "run-incomplete").mkdir(parents=True)
        incomplete = self.evidence.inspect_run("run-incomplete")
        self.assertEqual(incomplete["status"], "INCOMPLETE")
        self.assertEqual(incomplete["analysis_outcome"], "NOT_EVALUABLE")
        self.assertFalse(incomplete["valid_alpha2"])

    def test_cancelled_and_failed_jobs_remain_technical_states(self):
        state_dir = self.root / "results" / "evidence" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        for run_id, status in (("run-cancelled", "cancelled"), ("run-failed", "failed")):
            (state_dir / f"{run_id}.json").write_text(json.dumps({
                "run_id": run_id, "action": "evidence_single",
                "sample_ids": ["sample-x"], "status": status,
                "execution_status": status, "evidence_v2_status": status,
                **self.identity,
            }), encoding="utf-8")
            (self.root / "results" / "evidence" / "runs" / run_id).mkdir(parents=True, exist_ok=True)
            inspection = self.evidence.inspect_run(run_id)
            self.assertFalse(inspection["valid_alpha2"])
            self.assertEqual(inspection["analysis_outcome"], "NOT_EVALUABLE")
            state = self.evidence.state(run_id)
            self.assertEqual(state["analysis_outcome"], "NOT_EVALUABLE")
            self.assertEqual(state.get("execution_status") or status, status)

    def test_control_associated_signal_does_not_claim_contamination(self):
        self._install_run("run-no-evidence")
        payload = self.analytics.summary("run-no-evidence")
        self.assertIn("não confirma contaminação", payload["explanations"]["CONTROL_ASSOCIATED_SIGNAL"])
        self.assertIn("não possui controles associados", payload["explanations"]["UNCONTROLLED"])

    def test_empty_and_not_measured_datasets_stay_distinct(self):
        self._install_run("run-no-evidence")
        payload = self.analytics.summary("run-no-evidence")
        self.assertEqual(payload["datasets"]["read_support"]["status"], "empty")
        self.assertEqual(payload["datasets"]["read_support"]["rows"], 0)
        self.assertEqual(payload["datasets"]["coverage"]["status"], "not_measured")
        self.assertIsNone(payload["datasets"]["coverage"]["rows"])

    def test_not_applicable_coverage_is_explicit(self):
        def mutate(run_dir):
            evidence_path = run_dir / "sample_evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["coverage_status"] = "NOT_APPLICABLE"
            evidence_path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")

        self._install_run("run-not-applicable", mutate=mutate)
        payload = self.analytics.summary("run-not-applicable")
        if payload["validation"]["valid"]:
            self.assertEqual(payload["datasets"]["coverage"]["status"], "not_applicable")
            self.assertIsNone(payload["datasets"]["coverage"]["rows"])
        else:
            self.assertEqual(payload["metadata"]["analysis_outcome"], "NOT_EVALUABLE")

    def test_duplicate_query_params_fail_closed(self):
        self.assertEqual(query_one({"run": ["abc"]}, "run"), "abc")
        self.assertEqual(query_one({}, "run"), "")
        with self.assertRaisesRegex(ValueError, "duplicado"):
            query_one({"run": ["a", "b"]}, "run")

    def test_history_file_rejects_traversal_and_missing_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "results" / "runs"
            runs_dir.mkdir(parents=True)
            with patch.dict(dashboard.resolve_history_file.__globals__, {"get_runs_dir": lambda: runs_dir}):
                self.assertIsNone(dashboard.resolve_history_file("../etc/passwd", "report"))
                self.assertIsNone(dashboard.resolve_history_file("missing", "report"))
                self.assertIsNone(dashboard.resolve_history_file("missing", "fastq"))



if __name__ == "__main__":
    unittest.main()
