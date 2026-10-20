"""
Contrato de visibilidade da P&D experimental (mapeamento direto) no dashboard.

Estes testes fixam a separacao entre a arvore experimental e o fluxo canonico
Evidence V2 / Alpha.2: o dashboard pode exibir a P&D, mas nunca promove,
reinterpreta ou mistura os artefatos.
"""

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from dashboard import experimental  # noqa: E402


def write_run(runs_dir, run_id, *, contracts=None, promoted=True, metrics=True):
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    contracts = experimental.OUTPUT_CONTRACTS if contracts is None else contracts
    if promoted:
        (run_dir / "SUCCESS.json").write_text(json.dumps({
            "schema_version": "experimental-direct-map-success-v2",
            "contract_versions": contracts,
            "pipeline_version": experimental.PIPELINE_VERSION,
            "governance_state": "EXPERIMENTAL",
            "diagnostic": False,
            "run_id": run_id,
            "status": "done",
            "completed_at": "2026-08-04T10:00:00+00:00",
            "artifact_count": 14,
        }), encoding="utf-8")
    if metrics:
        (run_dir / "direct_map_metrics.json").write_text(json.dumps({
            "contract_versions": contracts,
            "governance_state": "EXPERIMENTAL",
            "diagnostic": False,
            "sample_id": "DEMO",
            "profile_id": experimental.PROFILE_ID,
            "profile_revision": experimental.PROFILE_REVISION,
            "pipeline_version": experimental.PIPELINE_VERSION,
            "input_reads": 100,
            "input_templates": 50,
            "invariants": {
                "state": "MEASURED",
                "coverage_cells_measured": 7,
                "coverage_cells_not_measured": 1,
            },
        }), encoding="utf-8")
    if promoted:
        (run_dir / "provenance.json").write_text(json.dumps({
            "contract_versions": contracts,
            "profile_id": experimental.PROFILE_ID,
            "profile_revision": experimental.PROFILE_REVISION,
            "pipeline_version": experimental.PIPELINE_VERSION,
        }), encoding="utf-8")
        (run_dir / "profile.json").write_text(json.dumps({
            "output_contracts": contracts,
            "profile_id": experimental.PROFILE_ID,
            "profile_revision": experimental.PROFILE_REVISION,
            "pipeline_version": experimental.PIPELINE_VERSION,
        }), encoding="utf-8")
        (run_dir / "panel_manifest.json").write_text("{}", encoding="utf-8")
        (run_dir / "baseline_comparison.json").write_text("{}", encoding="utf-8")
        (run_dir / "coverage_metrics.tsv").write_text("header\n", encoding="utf-8")
        manifest = run_dir / "artifact_manifest.json"
        manifest.write_text(json.dumps({"files": []}), encoding="utf-8")
        success = json.loads((run_dir / "SUCCESS.json").read_text(encoding="utf-8"))
        success["artifact_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (run_dir / "SUCCESS.json").write_text(json.dumps(success), encoding="utf-8")
    return run_dir


class ExperimentalDashboardVisibilityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out_root = Path(self._tmp.name)
        self.runs_dir = self.out_root.joinpath(*experimental.EXPERIMENT_SUBPATH)
        patcher = patch.dict(
            "os.environ", {"GENEIN_EXPERIMENTAL_OUT_ROOT": str(self.out_root)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)


    def test_runs_without_success_marker_are_never_listed(self):
        self.runs_dir.mkdir(parents=True)
        write_run(self.runs_dir, "run-promoted")
        write_run(self.runs_dir, "run-staging", promoted=False)
        payload = experimental.list_direct_map_runs()
        self.assertEqual([run["run_id"] for run in payload["runs"]], ["run-promoted"])
        with self.assertRaises(FileNotFoundError):
            experimental.direct_map_run("run-staging")

    def test_partial_run_is_never_exposed_as_current(self):
        # Um SUCCESS.json ao lado de metricas nao basta: sem o conjunto completo
        # de artefatos a execucao e `incomplete`, nunca vigente.
        self.runs_dir.mkdir(parents=True)
        for missing in ("provenance.json", "profile.json", "artifact_manifest.json",
                        "coverage_metrics.tsv"):
            run_dir = write_run(self.runs_dir, f"run-{missing.split('.')[0]}")
            (run_dir / missing).unlink()
            run = experimental.direct_map_run(run_dir.name)["run"]
            self.assertEqual(run["contract_state"], "incomplete", missing)
            self.assertIsNone(run.get("sample_id"), missing)
            self.assertIn(missing, run["note"])

    def test_tampered_artifact_manifest_is_not_current(self):
        # O hash ancorado no SUCCESS e a ancora de integridade do manifesto.
        self.runs_dir.mkdir(parents=True)
        run_dir = write_run(self.runs_dir, "run-tampered")
        (run_dir / "artifact_manifest.json").write_text(
            json.dumps({"files": ["adulterado"]}), encoding="utf-8"
        )
        run = experimental.direct_map_run("run-tampered")["run"]
        self.assertEqual(run["contract_state"], "incompatible")
        self.assertIsNone(run.get("sample_id"))
        self.assertIn("hash do SUCCESS", run["note"])

    def test_divergent_identity_between_artifacts_is_not_current(self):
        self.runs_dir.mkdir(parents=True)
        run_dir = write_run(self.runs_dir, "run-identity")
        provenance = json.loads((run_dir / "provenance.json").read_text(encoding="utf-8"))
        provenance["profile_revision"] = "1.1"
        (run_dir / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
        run = experimental.direct_map_run("run-identity")["run"]
        self.assertEqual(run["contract_state"], "incompatible")
        self.assertIsNone(run.get("sample_id"))
        self.assertIn("identidade", run["note"])

    def test_incompatible_contract_is_flagged_not_reinterpreted(self):
        self.runs_dir.mkdir(parents=True)
        legacy = dict(experimental.OUTPUT_CONTRACTS)
        legacy["metrics"] = "experimental-direct-map-metrics-v1"
        write_run(self.runs_dir, "run-legacy", contracts=legacy)
        run = experimental.list_direct_map_runs()["runs"][0]
        self.assertEqual(run["contract_state"], "incompatible")
        # Identidade permanece visivel, mas metricas nao sao lidas como atuais.
        self.assertIsNone(run.get("sample_id"))
        self.assertIsNone(run.get("invariant_state"))
        self.assertIn("nao reinterpretada", run["note"])

    def test_missing_root_is_reported_without_raising(self):
        payload = experimental.list_direct_map_runs()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["runs"], [])
        self.assertIn("GENEIN_EXPERIMENTAL_OUT_ROOT", payload["hint"])

    def test_experimental_root_inside_public_evidence_tree_is_refused(self):
        public_root = self.out_root / "evidence"
        with patch.dict(
            "os.environ",
            {"GENEIN_EXPERIMENTAL_OUT_ROOT": str(public_root / "rd")},
        ):
            with patch.object(experimental, "PUBLIC_EVIDENCE_ROOT", public_root):
                payload = experimental.list_direct_map_runs()
        self.assertFalse(payload["available"])
        self.assertIn("arvore publica", payload["error"])

    def test_run_id_and_artifact_type_are_allowlisted(self):
        self.runs_dir.mkdir(parents=True)
        write_run(self.runs_dir, "run-001")
        self.assertEqual(
            experimental.direct_map_artifact("run-001", "metrics").name,
            "direct_map_metrics.json",
        )
        for hostile in ("../escape", "run-001/..", "", "a" * 200):
            with self.assertRaises(ValueError):
                experimental.direct_map_artifact(hostile, "metrics")
        for hostile_type in ("../../../etc/passwd", "primary.bam", ""):
            with self.assertRaises(ValueError):
                experimental.direct_map_artifact("run-001", hostile_type)



if __name__ == "__main__":
    unittest.main()
