import json
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from common import sha256_file, write_json_atomic, write_tsv_atomic
from activation_policy import POLICY_IDENTITY_FIELDS, load_public_activation_policy, policy_identity
from classify_sample import classify
from evidence_contract import not_evaluable_document
from evidence_dashboard import EvidenceDashboardService
import finalize_batch
import finalize_panel
import finalize_run
from finalize_batch import validate_batch_identity, validate_source_sample
from run_state import initial_state
from validate_run_artifacts import validate_commit_metadata


def fastq(path: Path, mate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"@template/" + str(mate) + "\nACGT\n+\nIIII\n", encoding="utf-8")


class ManifestServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        fastq(self.root / "data/raw/a_R1.fastq", 1)
        fastq(self.root / "data/raw/a_R2.fastq", 2)
        self.service = EvidenceDashboardService(self.root)
        self.row = {
            "batch_id": "batch-a", "sample_id": "sample-a", "role": "sample",
            "library_mode": "shotgun", "umi_mode": "none",
            "r1": "data/raw/a_R1.fastq", "r2": "data/raw/a_R2.fastq", "expected_target": "",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_manifest_is_validated_and_promoted_as_tsv_json_pair(self):
        result = self.service.save_manifest([self.row], "manifest-a")
        self.assertTrue(result["valid"])
        self.assertIn("UNCONTROLLED", result["warnings"][0])
        self.assertTrue((self.root / "data/manifests/manifest-a.tsv").is_file())
        self.assertTrue((self.root / "data/manifests/manifest-a.json").is_file())

    def test_duplicate_sample_and_path_are_rejected(self):
        duplicate = dict(self.row)
        result = self.service.validate_manifest([self.row, duplicate])
        self.assertFalse(result["valid"])
        self.assertTrue(any("duplicado" in error for item in result["errors"] for error in item["errors"]))

    def test_incomplete_run_cannot_export_artifact(self):
        state = self.root / "results/evidence/state/run-safe.json"
        write_json_atomic(state, initial_state("run-safe", "evidence_single", ["sample-a"], None))
        with self.assertRaises((FileNotFoundError, ValueError)):
            self.service.artifact("run-safe", "sample_evidence")


class TransactionTests(unittest.TestCase):
    def active_identity(self) -> dict:
        return policy_identity(load_public_activation_policy())

    def provenance(self, artifacts: dict[str, Path] | None = None) -> dict:
        config = ROOT / "config/evidence_profiles.json"
        records = artifacts or {"evidence_profiles": config}
        return {
            "schema_version": "2.0",
            "pipeline_version": "2.0.0-alpha.2",
            "platform": platform.platform(),
            "config_path": str(config.resolve()),
            "config_sha256": sha256_file(config),
            "parameters": {"fixture": "transactional"},
            "artifacts": {
                name: {
                    "path": str(path.resolve()),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for name, path in records.items()
            },
            "tools": {
                "python3": {
                    "version": sys.version.splitlines()[0],
                    "executable": str(Path(sys.executable).resolve()),
                    "sha256": sha256_file(sys.executable),
                },
            },
        }

    def make_staging(self, root: Path) -> Path:
        staging = root / ".staging/run-safe"
        staging.mkdir(parents=True)
        from aggregate_hsps import FIELDS as FRAGMENT_FIELDS
        from build_hsp_evidence import FIELDS as HSP_FIELDS
        from build_loci import FIELDS as LOCUS_FIELDS
        from build_template_lineage import FIELDS as LINEAGE_FIELDS
        from competitive_hits import FIELDS as COMPETITIVE_FIELDS
        from summarize_coverage import FIELDS as COVERAGE_FIELDS
        from summarize_read_support import FIELDS as READ_SUPPORT_FIELDS
        headers = {
            "fragment_evidence.tsv": "\t".join(FRAGMENT_FIELDS) + "\n",
            "locus_evidence.tsv": "\t".join(LOCUS_FIELDS) + "\n",
            "competitive_hits.tsv": "\t".join(COMPETITIVE_FIELDS) + "\n",
            "read_support.tsv": "\t".join(READ_SUPPORT_FIELDS) + "\n",
            "coverage.tsv": "\t".join(COVERAGE_FIELDS) + "\n",
            "hsp_evidence.tsv": "\t".join(HSP_FIELDS) + "\n",
            "template_lineage.tsv": "\t".join(LINEAGE_FIELDS) + "\n",
        }
        for name, header in headers.items():
            (staging / name).write_text(header, encoding="utf-8")
        provenance = self.provenance()
        (staging / "sample_evidence.json").write_text(
            json.dumps(classify(
                "sample-a", [], [], [], [], "UNCONTROLLED", "unknown",
                provenance=provenance, run_id="run-safe",
            )) + "\n",
            encoding="utf-8",
        )
        (staging / "runtime_preflight.json").write_text('{"valid": true}\n', encoding="utf-8")
        write_json_atomic(staging / "provenance.json", provenance)
        (staging / "evidence_report.md").write_text("# experimental\n", encoding="utf-8")
        return staging

    def make_panel_staging(self, root: Path, panel_id: str = "panel-safe") -> Path:
        staging = root / ".staging" / panel_id
        (staging / "blast").mkdir(parents=True)
        (staging / "bowtie2").mkdir()
        categories = [
            "TARGET_VIRUS", "NEAR_NON_TARGET_VIRUS", "HOST",
            "VECTOR_ADAPTER", "KNOWN_CONTAMINANT", "SYNTHETIC_SEQUENCE",
        ]
        fasta_lines = []
        label_lines = ["sseqid\tcategory\ttaxon\tsegment"]
        for index, category in enumerate(categories, 1):
            sequence_id = f"seq{index}"
            fasta_lines.extend([f">{sequence_id}", "ACGTACGT"])
            label_lines.append(f"{sequence_id}\t{category}\ttaxon{index}\tunsegmented")
        (staging / "panel.fa").write_text("\n".join(fasta_lines) + "\n", encoding="utf-8")
        (staging / "labels.tsv").write_text("\n".join(label_lines) + "\n", encoding="utf-8")
        for extension in ("nhr", "nin", "nsq"):
            (staging / "blast" / f"panel.{extension}").write_bytes(b"index")
        for extension in ("1", "2", "3", "4", "rev.1", "rev.2"):
            (staging / "bowtie2" / f"panel.{extension}.bt2").write_bytes(b"index")
        (staging / "makeblastdb.log").write_text("synthetic\n", encoding="utf-8")
        return staging

    def make_batch_staging(self, root: Path):
        staging = root / ".staging/batch-run"
        child_source = self.make_staging(root / "child-source")
        child = staging / "samples/sample-a"
        child.parent.mkdir(parents=True)
        child_source.replace(child)
        child_provenance = json.loads((child / "provenance.json").read_text(encoding="utf-8"))
        evidence = classify(
            "sample-a", [], [], [], [], "UNCONTROLLED", "unknown",
            provenance=child_provenance, run_id="child-run",
        )
        write_json_atomic(child / "sample_evidence.json", evidence)
        child_state = initial_state("child-run", "evidence_single", ["sample-a"], None)
        child_state.update({
            "status": "done", "execution_status": evidence["execution_status"],
            "analysis_outcome": evidence["analysis_outcome"],
            "evidence_level": evidence["evidence_level"],
        })
        write_json_atomic(child / "run_state.json", child_state)
        write_json_atomic(child / "SUCCESS.json", {
            "run_id": "child-run", "status": "done", "shadow_mode": False,
            **self.active_identity(),
        })
        batch_sample = {
            "sample_id": "sample-a",
            "child_run_id": "child-run",
            "execution_status": evidence["execution_status"],
            "analysis_outcome": evidence["analysis_outcome"],
            "evidence_level": evidence["evidence_level"],
            "reported_conclusion": evidence["reported_conclusion"],
            "caveats": evidence["caveats"],
            "promotion_gates": evidence["promotion_gates"],
            **self.active_identity(),
        }
        write_json_atomic(staging / "batch_evidence.json", {
            "schema_version": "2.0",
            "pipeline_version": "2.0.0-alpha.2",
            "run_id": "batch-run",
            "batch_id": "batch-a",
            **self.active_identity(),
            "shadow_mode": False,
            "reported_conclusion": "EVIDENCE_RECOVERED",
            "samples": [batch_sample],
        })
        from evaluate_controls import FIELDS as CONTROL_FIELDS
        from validate_manifest import FIELDS as BATCH_MANIFEST_FIELDS
        batch_manifest = staging / "batch_manifest.tsv"
        write_tsv_atomic(batch_manifest, [{
            "batch_id": "batch-a", "sample_id": "sample-a", "role": "sample",
            "library_mode": "unknown", "umi_mode": "none",
            "r1": str(ROOT / "scripts/tests/evidence/fixtures/query_sequences.txt"),
            "r2": str(ROOT / "scripts/tests/evidence/fixtures/query_sequences.txt"),
            "expected_target": "",
        }], BATCH_MANIFEST_FIELDS)
        write_tsv_atomic(staging / "control_status.tsv", [{
            "batch_id": "batch-a", "sample_id": "sample-a", "target": "UNSPECIFIED",
            "control_status": "UNCONTROLLED", "normalization": "rpm_post_qc",
            "sample_rpm": "0.00000000", "maximum_negative_rpm": "0.00000000",
            "sample_to_negative_ratio": "", "shared_sequence": "FALSE",
            "index_hopping": "FALSE", "donor_sample_id": "",
            "donor_to_receiver_ratio": "",
        }], CONTROL_FIELDS)
        (staging / "batch_report.md").write_text("# batch\n", encoding="utf-8")
        batch_provenance = self.provenance({"batch_manifest": batch_manifest})
        batch_provenance["artifacts"]["batch_manifest"]["path"] = "batch_manifest.tsv"
        write_json_atomic(staging / "provenance.json", batch_provenance)
        run_map = root / "run-map.tsv"
        run_map.write_text(
            "sample_id\trun_id\nsample-a\tchild-run\n",
            encoding="utf-8",
        )
        state = root / "state/batch-run.json"
        write_json_atomic(
            state,
            initial_state("batch-run", "evidence_batch", ["sample-a"], "batch-a"),
        )
        return staging, state, run_map

    def test_success_marker_exists_only_after_atomic_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            state = root / "state/run-safe.json"
            write_json_atomic(state, initial_state("run-safe", "evidence_single", ["sample-a"], None))
            final = root / "runs/run-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(staging.exists())
            self.assertTrue((final / "SUCCESS.json").is_file())
            self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["status"], "done")
            policy = self.active_identity()
            for path in (state, final / "run_state.json", final / "sample_evidence.json", final / "SUCCESS.json"):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    {field: value[field] for field in POLICY_IDENTITY_FIELDS},
                    policy,
                )

    def test_canonical_evidence_json_is_downloadable_only_after_valid_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            config = project / "config"
            config.mkdir()
            for name in ("evidence_profiles.json", "evidence_activation.json"):
                shutil.copy2(ROOT / "config" / name, config / name)
            evidence_root = project / "results/evidence"
            staging = self.make_staging(evidence_root)
            state = evidence_root / "state/run-safe.json"
            write_json_atomic(
                state,
                initial_state("run-safe", "evidence_single", ["sample-a"], None),
            )
            final = evidence_root / "runs/run-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            service = EvidenceDashboardService(project)
            public = service.result("run-safe")
            self.assertIn("sample_evidence", public["artifacts"])
            self.assertEqual(
                service.artifact("run-safe", "sample_evidence").name,
                "sample_evidence.json",
            )

    def test_run_success_marker_is_absent_at_directory_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            state = root / "state/run-safe.json"
            write_json_atomic(state, initial_state("run-safe", "evidence_single", ["sample-a"], None))
            final = root / "runs/run-safe"
            real_promote = finalize_run.promote_directory
            observed = {}

            def inspect_promotion(source, target):
                observed["success_before_promotion"] = (source / "SUCCESS.json").exists()
                real_promote(source, target)

            argv = [
                "finalize_run.py", "--state", str(state),
                "--staging", str(staging), "--final", str(final),
            ]
            with (
                patch.object(finalize_run, "promote_directory", side_effect=inspect_promotion),
                patch.object(sys, "argv", argv),
            ):
                finalize_run.main()
            self.assertFalse(observed["success_before_promotion"])
            self.assertTrue((final / "SUCCESS.json").is_file())

    def test_partial_file_prevents_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            (staging / ".interrupted.tmp").write_text("partial", encoding="utf-8")
            state = root / "state/run-safe.json"
            write_json_atomic(state, initial_state("run-safe", "evidence_single", ["sample-a"], None))
            final = root / "runs/run-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(final.exists())
            self.assertFalse((staging / "SUCCESS.json").exists())

    def test_existing_run_is_preserved_when_replacement_cannot_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            final = root / "runs/run-safe"
            final.mkdir(parents=True)
            (final / "SUCCESS.json").write_text('{"status":"done"}\n', encoding="utf-8")
            (final / "old-result.txt").write_text("previous\n", encoding="utf-8")
            state = root / "state/run-safe.json"
            write_json_atomic(state, initial_state("run-safe", "evidence_single", ["sample-a"], None))
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((final / "old-result.txt").read_text(encoding="utf-8"), "previous\n")
            self.assertFalse((staging / "SUCCESS.json").exists())

    def test_success_marker_is_removed_if_directory_promotion_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            state = root / "state/run-safe.json"
            write_json_atomic(state, initial_state("run-safe", "evidence_single", ["sample-a"], None))
            blocked_parent = root / "blocked-parent"
            blocked_parent.write_text("not a directory\n", encoding="utf-8")
            final = blocked_parent / "run-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(staging.is_dir())
            self.assertFalse((staging / "SUCCESS.json").exists())
            self.assertFalse((staging / "artifact_manifest.json").exists())

            retry_final = root / "runs/run-safe"
            retry = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state), "--staging", str(staging), "--final", str(retry_final),
            ], capture_output=True, text=True)
            self.assertEqual(retry.returncode, 0, retry.stderr)
            self.assertTrue((retry_final / "SUCCESS.json").is_file())

    def test_state_and_evidence_identity_mismatch_prevents_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            state_path = root / "state/run-safe.json"
            write_json_atomic(
                state_path,
                initial_state("different-run", "evidence_single", ["sample-a"], None),
            )
            final = root / "runs/run-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state_path), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(final.exists())
            self.assertFalse((staging / "SUCCESS.json").exists())

    def test_each_policy_identity_mismatch_prevents_promotion(self):
        for field in POLICY_IDENTITY_FIELDS:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                staging = self.make_staging(root)
                evidence_path = staging / "sample_evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence[field] = not evidence[field] if field == "shadow_mode" else "divergent"
                write_json_atomic(evidence_path, evidence)
                state_path = root / "state/run-safe.json"
                write_json_atomic(
                    state_path,
                    initial_state("run-safe", "evidence_single", ["sample-a"], None),
                )
                final = root / "runs/run-safe"
                result = subprocess.run([
                    sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                    "--state", str(state_path), "--staging", str(staging), "--final", str(final),
                ], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(final.exists())
                self.assertFalse((staging / "SUCCESS.json").exists())

    def test_success_identity_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            state_path = root / "state/run-safe.json"
            write_json_atomic(
                state_path,
                initial_state("run-safe", "evidence_single", ["sample-a"], None),
            )
            final = root / "runs/run-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state_path), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            success_path = final / "SUCCESS.json"
            success = json.loads(success_path.read_text(encoding="utf-8"))
            success["profile_version"] = "divergent"
            write_json_atomic(success_path, success)
            errors = validate_commit_metadata(final)
            self.assertTrue(any("policy identity" in error for error in errors))

    def test_not_evaluable_run_preserves_active_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            write_json_atomic(
                staging / "sample_evidence.json",
                not_evaluable_document(
                    "sample-a", "run-safe", "simulated scientific-stage failure",
                    provenance=json.loads(
                        (staging / "provenance.json").read_text(encoding="utf-8")
                    ),
                ),
            )
            state_path = root / "state/run-safe.json"
            write_json_atomic(
                state_path,
                initial_state("run-safe", "evidence_single", ["sample-a"], None),
            )
            final = root / "runs/run-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_run.py"),
                "--state", str(state_path), "--staging", str(staging), "--final", str(final),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads((final / "sample_evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["analysis_outcome"], "NOT_EVALUABLE")
            self.assertEqual(evidence["evidence_level"], "NOT_EVALUABLE")
            self.assertEqual(
                {field: evidence[field] for field in POLICY_IDENTITY_FIELDS},
                self.active_identity(),
            )

    def test_state_write_failure_rolls_back_promoted_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_staging(root)
            state_path = root / "state/run-safe.json"
            write_json_atomic(
                state_path,
                initial_state("run-safe", "evidence_single", ["sample-a"], None),
            )
            final = root / "runs/run-safe"
            real_write = finalize_run.write_json_atomic

            def fail_external_state(path, value):
                if Path(path) == state_path and final.exists():
                    raise OSError("simulated state persistence failure")
                return real_write(path, value)

            argv = [
                "finalize_run.py", "--state", str(state_path),
                "--staging", str(staging), "--final", str(final),
            ]
            with (
                patch.object(finalize_run, "write_json_atomic", side_effect=fail_external_state),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(OSError, "simulated state"),
            ):
                finalize_run.main()
            self.assertFalse((final / "SUCCESS.json").exists())
            self.assertTrue(staging.is_dir())
            self.assertFalse((staging / "SUCCESS.json").exists())
            self.assertFalse((staging / "artifact_manifest.json").exists())

    def test_panel_promotion_failure_leaves_no_success_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_panel_staging(root)
            blocked_parent = root / "blocked-parent"
            blocked_parent.write_text("not a directory\n", encoding="utf-8")
            final = blocked_parent / "panel-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_panel.py"),
                "--staging", str(staging), "--final", str(final),
                "--panel-id", "panel-safe",
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(staging.is_dir())
            self.assertFalse((staging / "SUCCESS.json").exists())
            self.assertFalse((staging / "panel_manifest.json").exists())

    def test_panel_manifest_covers_logs_before_atomic_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_panel_staging(root)
            final = root / "panels/panel-safe"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evidence/finalize_panel.py"),
                "--staging", str(staging), "--final", str(final),
                "--panel-id", "panel-safe",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(
                (final / "panel_manifest.json").read_text(encoding="utf-8"),
            )
            self.assertIn("makeblastdb.log", manifest["files"])
            self.assertTrue((final / "SUCCESS.json").is_file())
            self.assertFalse(staging.exists())

    def test_panel_success_marker_is_absent_at_directory_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self.make_panel_staging(root)
            final = root / "panels/panel-safe"
            real_promote = finalize_panel.promote_directory
            observed = {}

            def inspect_promotion(source, target):
                observed["success_before_promotion"] = (source / "SUCCESS.json").exists()
                real_promote(source, target)

            argv = [
                "finalize_panel.py", "--staging", str(staging),
                "--final", str(final), "--panel-id", "panel-safe",
            ]
            with (
                patch.object(finalize_panel, "promote_directory", side_effect=inspect_promotion),
                patch.object(sys, "argv", argv),
            ):
                finalize_panel.main()
            self.assertFalse(observed["success_before_promotion"])
            self.assertTrue((final / "SUCCESS.json").is_file())

    def test_batch_success_marker_is_absent_at_directory_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging, state, run_map = self.make_batch_staging(root)
            final = root / "runs/batch-run"
            real_promote = finalize_batch.promote_directory
            observed = {}

            def inspect_promotion(source, target):
                observed["success_before_promotion"] = (source / "SUCCESS.json").exists()
                real_promote(source, target)

            argv = [
                "finalize_batch.py", "--state", str(state),
                "--staging", str(staging), "--final", str(final),
                "--run-map", str(run_map),
            ]
            with (
                patch.object(finalize_batch, "promote_directory", side_effect=inspect_promotion),
                patch.object(sys, "argv", argv),
            ):
                finalize_batch.main()
            self.assertFalse(observed["success_before_promotion"])
            self.assertTrue((final / "SUCCESS.json").is_file())
            expected = self.active_identity()
            batch = json.loads((final / "batch_evidence.json").read_text(encoding="utf-8"))
            success = json.loads((final / "SUCCESS.json").read_text(encoding="utf-8"))
            child_evidence = json.loads(
                (final / "samples/sample-a/sample_evidence.json").read_text(encoding="utf-8")
            )
            child_success = json.loads(
                (final / "samples/sample-a/SUCCESS.json").read_text(encoding="utf-8")
            )
            for value in (batch, batch["samples"][0], success, child_evidence, child_success):
                self.assertEqual(
                    {field: value[field] for field in POLICY_IDENTITY_FIELDS},
                    expected,
                )
            self.assertEqual(batch["reported_conclusion"], "EVIDENCE_RECOVERED")
            self.assertEqual(batch["samples"][0]["reported_conclusion"], "NO_EVIDENCE_RECOVERED")
            self.assertTrue((final / "batch_manifest.tsv").is_file())
            manifest = json.loads((final / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("batch_manifest.tsv", manifest["files"])
            self.assertEqual(validate_commit_metadata(final), [])
            batch["batch_id"] = "tampered"
            write_json_atomic(final / "batch_evidence.json", batch)
            self.assertTrue(any(
                "batch evidence hash mismatch" in error
                for error in validate_commit_metadata(final)
            ))

    def test_batch_rejects_child_run_relabeling_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            child = Path(tmp) / "samples/sample-a"
            child.mkdir(parents=True)
            (child / "SUCCESS.json").write_text(
                '{"run_id":"wrong-child","status":"done"}\n', encoding="utf-8",
            )
            (child / "sample_evidence.json").write_text(
                json.dumps(classify(
                    "sample-a", [], [], [], [], "UNCONTROLLED", "unknown",
                    run_id="expected-child",
                )) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "run_id da execução filha"):
                validate_source_sample(
                    child, {"sample_id": "sample-a", "run_id": "expected-child"},
                    self.active_identity(),
                )

    def test_batch_identity_must_match_state_and_run_map(self):
        state = initial_state(
            "batch-run", "evidence_batch", ["sample-a", "sample-b"], "batch-a",
        )
        batch = {
            "run_id": "batch-run", "batch_id": "batch-a", **self.active_identity(),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / ".staging/batch-run"
            final = root / "runs/batch-run"
            rows = [
                {"sample_id": "sample-a", "run_id": "child-a"},
                {"sample_id": "sample-b", "run_id": "child-b"},
            ]
            validate_batch_identity(state, batch, rows, staging, final)
            rows.reverse()
            with self.assertRaisesRegex(ValueError, "run map samples"):
                validate_batch_identity(state, batch, rows, staging, final)


if __name__ == "__main__":
    unittest.main()
