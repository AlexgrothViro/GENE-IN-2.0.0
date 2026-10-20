import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

import write_provenance
from classify_sample import classify
from collect_batch_metrics import collect, fastq_reads
from common import (
    build_artifact_manifest, sha256_file, validate_artifact_manifest,
    write_json_atomic,
)
from evaluate_controls import evaluate
from validate_run_artifacts import validate_provenance


def manifest_row(sample: str, role: str = "sample") -> dict[str, str]:
    return {
        "batch_id": "batch-a", "sample_id": sample, "role": role,
        "library_mode": "shotgun", "umi_mode": "none",
        "r1": "r1.fastq", "r2": "r2.fastq", "expected_target": "virus",
    }


def metric_row(sample: str, role_rpm: str, nonhost: str = "NA") -> dict[str, str]:
    return {
        "batch_id": "batch-a", "sample_id": sample, "target": "virus",
        "expected_target": "virus", "rpm_post_qc": role_rpm,
        "rpm_nonhost": nonhost, "sequence_hashes": "",
        "positive_control_qualification": "NOT_QUALIFIED",
    }


class BatchMetricSemanticsTests(unittest.TestCase):
    def make_evidence(self, root: Path, sample: str = "sample-a") -> tuple[Path, dict[str, str]]:
        evidence_root = root / "results/evidence"
        run_id = f"run-{sample}"
        run_dir = evidence_root / "runs" / run_id
        run_dir.mkdir(parents=True)
        write_json_atomic(
            run_dir / "sample_evidence.json",
            classify(sample, [], [], [], [], "UNCONTROLLED", "shotgun", run_id=run_id),
        )
        write_json_atomic(run_dir / "SUCCESS.json", {"run_id": run_id, "status": "done"})
        (run_dir / "fragment_evidence.tsv").write_text(
            "qseqid\tsequence_sha256\n", encoding="utf-8",
        )
        return evidence_root, {sample: run_id}

    def write_fastp(self, root: Path, sample: str, total_reads: object) -> None:
        write_json_atomic(
            root / "results/qc" / f"{sample}_fastp.json",
            {"summary": {"after_filtering": {"total_reads": total_reads}}},
        )

    def test_missing_and_zero_post_qc_denominators_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_root, run_ids = self.make_evidence(root)
            with self.assertRaisesRegex(ValueError, "not measured"):
                collect([manifest_row("sample-a")], root, evidence_root, run_ids)
            self.write_fastp(root, "sample-a", 0)
            with self.assertRaisesRegex(ValueError, "measured as zero"):
                collect([manifest_row("sample-a")], root, evidence_root, run_ids)

    def test_missing_nonhost_is_not_applicable_but_measured_zero_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_root, run_ids = self.make_evidence(root)
            self.write_fastp(root, "sample-a", 100)
            rows = collect([manifest_row("sample-a")], root, evidence_root, run_ids)
            self.assertEqual(rows[0]["rpm_post_qc"], "0.00000000")
            self.assertEqual(rows[0]["rpm_nonhost"], "NA")
            nonhost = root / "data/host_removed/sample-a_R1.host_removed.fastq.gz"
            nonhost.parent.mkdir(parents=True)
            nonhost.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "measured as zero"):
                collect([manifest_row("sample-a")], root, evidence_root, run_ids)

    def test_incomplete_fastq_is_not_silently_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.fastq"
            path.write_text("@r\nACGT\n+\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete record"):
                fastq_reads(path)

    def test_control_evaluation_rejects_unmeasured_or_incomparable_metrics(self):
        manifest = [manifest_row("sample-a"), manifest_row("negative", "negative_library")]
        with self.assertRaisesRegex(ValueError, "rpm_post_qc is not measured"):
            evaluate(manifest, [metric_row("sample-a", "NA"), metric_row("negative", "0")])
        with self.assertRaisesRegex(ValueError, "rpm_nonhost is not measured"):
            evaluate(
                manifest,
                [metric_row("sample-a", "10", "10"), metric_row("negative", "0", "NA")],
            )

    def test_measured_zero_negative_remains_distinct_from_missing(self):
        manifest = [manifest_row("sample-a"), manifest_row("negative", "negative_library")]
        rows = evaluate(
            manifest,
            [metric_row("sample-a", "10"), metric_row("negative", "0")],
        )
        sample = next(row for row in rows if row["sample_id"] == "sample-a")
        self.assertEqual(sample["control_status"], "CONTROL_NOT_DETECTED")
        self.assertEqual(sample["maximum_negative_rpm"], "0.00000000")

    def test_nan_and_infinite_metrics_are_rejected(self):
        manifest = [manifest_row("sample-a")]
        for value in ("nan", "inf", "-1"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "invalid"):
                evaluate(manifest, [metric_row("sample-a", value)])


class ArtifactIntegrityTests(unittest.TestCase):
    def tool_record(self) -> dict[str, str]:
        return {
            "version": sys.version.splitlines()[0],
            "executable": str(Path(sys.executable).resolve()),
            "sha256": sha256_file(sys.executable),
        }

    def test_internal_provenance_path_survives_atomic_directory_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / ".staging/run-a"
            final = root / "runs/run-a"
            staging.mkdir(parents=True)
            artifact = staging / "metric.tsv"
            artifact.write_text("metric\n0\n", encoding="utf-8")
            output = staging / "provenance.json"
            argv = [
                "write_provenance.py", "--out", str(output),
                "--config", str(ROOT / "config/evidence_profiles.json"),
                "--artifact", f"primary_metric={artifact}",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(write_provenance, "tool_record", return_value=self.tool_record()),
            ):
                write_provenance.main()
            provenance = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(provenance["artifacts"]["primary_metric"]["path"], "metric.tsv")
            final.parent.mkdir(parents=True)
            staging.replace(final)
            validate_provenance(final / "provenance.json")

            (final / "metric.tsv").write_text("metric\n1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provenance artifact hash mismatch"):
                validate_provenance(final / "provenance.json")

    def test_internal_provenance_path_cannot_escape_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run-a"
            run.mkdir()
            outside = root / "outside.tsv"
            outside.write_text("metric\n0\n", encoding="utf-8")
            provenance = {
                "schema_version": "2.0", "pipeline_version": "2.0.0-alpha.2",
                "platform": "test", "config_path": str(
                    (ROOT / "config/evidence_profiles.json").resolve()
                ),
                "config_sha256": sha256_file(ROOT / "config/evidence_profiles.json"),
                "parameters": {},
                "artifacts": {
                    "escaped": {
                        "path": "../outside.tsv", "size": outside.stat().st_size,
                        "sha256": sha256_file(outside),
                    },
                },
                "tools": {"python3": self.tool_record()},
            }
            write_json_atomic(run / "provenance.json", provenance)
            with self.assertRaisesRegex(ValueError, "escapes run directory"):
                validate_provenance(run / "provenance.json")

    def test_manifest_rejects_invalid_metadata_and_hash_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.txt"
            artifact.write_text("measured zero: 0\n", encoding="utf-8")
            manifest = build_artifact_manifest(root)
            self.assertEqual(validate_artifact_manifest(root, manifest), [])
            malformed = json.loads(json.dumps(manifest))
            malformed["files"]["artifact.txt"]["size"] = True
            self.assertIn("invalid artifact size metadata", "\n".join(
                validate_artifact_manifest(root, malformed)
            ))
            artifact.write_text("tampered\n", encoding="utf-8")
            errors = "\n".join(validate_artifact_manifest(root, manifest))
            self.assertIn("artifact size mismatch", errors)
            self.assertIn("artifact hash mismatch", errors)


if __name__ == "__main__":
    unittest.main()
