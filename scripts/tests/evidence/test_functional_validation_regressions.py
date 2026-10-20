import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/pipeline"))
sys.path.insert(0, str(ROOT / "scripts/evidence"))
sys.path.insert(0, str(ROOT / "scripts/lib"))

from select_best_adjusted_hit import REQUIRED_FIELDS, select_best
from adj_identity import compute_adjusted
from evidence_dashboard import EvidenceDashboardService
import ux_dashboard


def write_adjusted(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(REQUIRED_FIELDS)
        writer.writerows(rows)


def row(query: str, adjusted: str, coverage: str = "0.5") -> list[str]:
    return [query, "ref", "99", "50", "1e-20", "100", "100", coverage, adjusted]


class AdjustedHitSelectionTests(unittest.TestCase):
    def test_adjusted_identity_uses_query_span_not_gapped_alignment_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fasta = root / "query.fa"
            blast = root / "blast.tsv"
            output = root / "adjusted.tsv"
            fasta.write_text(">q\nACGTACGTACGTACGTACGT\n", encoding="utf-8")
            blast.write_text(
                "q\tref\t80\t25\t5\t1\t1\t20\t1\t25\t1e-5\t40\t20\t100\n",
                encoding="utf-8",
            )
            compute_adjusted(blast, fasta, output)
            with output.open(encoding="utf-8", newline="") as handle:
                row_value = next(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(float(row_value["aln_cov"]), 1.0)
            self.assertEqual(float(row_value["adj_identity"]), 80.0)

    def test_one_row_and_many_rows_are_selected_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "adjusted.tsv"
            write_adjusted(path, [row("only", "70")])
            self.assertIn("only vs ref", select_best(path))
            rows = [row(f"q-{index:05d}", str(index % 97)) for index in range(20000)]
            rows.extend([row("z-tie", "99"), row("a-tie", "99")])
            write_adjusted(path, rows)
            first = select_best(path)
            self.assertIn("a-tie vs ref", first)
            for _ in range(4):
                self.assertEqual(select_best(path), first)

    def test_empty_header_only_invalid_header_and_invalid_numeric_are_distinct(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "scripts/tests/evidence") as tmp:
            root = Path(tmp)
            empty = root / "empty.tsv"
            empty.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                select_best(empty)
            header = root / "header.tsv"
            write_adjusted(header, [])
            self.assertEqual(select_best(header), "")
            invalid_header = root / "invalid-header.tsv"
            invalid_header.write_text("qseqid\twrong\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid header"):
                select_best(invalid_header)
            invalid_numeric = root / "invalid-numeric.tsv"
            write_adjusted(invalid_numeric, [row("q", "not-a-number")])
            with self.assertRaisesRegex(ValueError, "numeric"):
                select_best(invalid_numeric)
            with self.assertRaisesRegex(OSError, "cannot read"):
                select_best(root / "missing.tsv")


class MinimalReportIntegrationTests(unittest.TestCase):
    @staticmethod
    def git_bash() -> Path | None:
        if os.name != "nt":
            bash = shutil.which("bash")
            return Path(bash) if bash else None
        candidates = [
            Path(r"C:\Program Files\Git\bin\bash.exe"),
            Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
        ]
        return next((path for path in candidates if path.is_file()), None)

    @staticmethod
    def posix(path: Path) -> str:
        resolved = path.resolve()
        if os.name != "nt":
            return resolved.as_posix()
        drive = resolved.drive.rstrip(":").lower()
        return f"/{drive}/{resolved.as_posix().split(':', 1)[1].lstrip('/')}"

    @unittest.skipUnless(git_bash.__func__(), "Bash is required for the real pipeline/report_minimal.sh flow")
    def test_real_report_flow_uses_unique_explicit_adaptation_and_source_hash(self):
        bash = self.git_bash()
        with tempfile.TemporaryDirectory(dir=ROOT / "scripts/tests/evidence") as tmp:
            root = Path(tmp)
            contigs = root / "contigs.fa"
            blast = root / "blast.tsv"
            report = root / "results/reports/sample_summary.md"
            report.parent.mkdir(parents=True)
            (root / "results/blast").mkdir(parents=True)
            contigs.write_text(">contig-1\n" + "A" * 100 + "\n", encoding="utf-8")
            blast.write_text(
                "contig-1\tref-1\t99\t50\t0\t0\t1\t50\t1\t50\t1e-20\t100\t100\t100\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["EVIDENCE_RUN_ID"] = "dashboard-run-00000001"
            result = subprocess.run([
                str(bash), "-c",
                'export PATH="/usr/bin:/bin:$PATH"; mkdir() { :; }; export -f mkdir; exec "$@"', "bash",
                "scripts/pipeline/report_minimal.sh", "--sample", "sample",
                "--contigs", self.posix(contigs), "--blast", self.posix(blast),
                "--out", self.posix(report),
            ], cwd=ROOT, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            adapted_path = root / "results/blast/sample_legacy_evidence.json"
            labeled_path = root / "results/blast/sample_labeled_hits.tsv"
            adapted = json.loads(adapted_path.read_text(encoding="utf-8"))
            trace = adapted["provenance"]["legacy_adaptation"]
            self.assertEqual(adapted["evidence_level"], "NOT_EVALUABLE")
            self.assertEqual(trace["adaptation_id"], "report-1.1-sample-dashboard-run-00000001")
            expected_hash = hashlib.sha256(labeled_path.read_bytes()).hexdigest()
            self.assertEqual(adapted["provenance"]["source_artifact_sha256"], expected_hash)


class DashboardReservationTests(unittest.TestCase):
    def test_individual_dashboard_job_passes_its_private_reservation_to_the_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = EvidenceDashboardService(Path(tmp))
            params = {
                "run_id": "dashboard-run-00000001", "sample": "sample-a",
                "assembler": "spades", "db": "ptv",
            }
            with patch.object(ux_dashboard, "EVIDENCE_SERVICE", service):
                ux_dashboard.initialize_evidence_dashboard_state("evidence_pipeline", params)
                state = json.loads(
                    (service.evidence_root / "state/dashboard-run-00000001.json").read_text(encoding="utf-8")
                )
                _, environment = ux_dashboard.build_command("evidence_pipeline", params)
            self.assertEqual(state["reservation"]["status"], "reserved")
            self.assertNotIn(params["reservation_token"], json.dumps(state))
            self.assertEqual(environment["EVIDENCE_RESERVATION_TOKEN"], params["reservation_token"])
            self.assertEqual(ux_dashboard.params_for_log(params)["reservation_token"], "[redacted]")

    def test_v2_failure_is_reported_separately_when_official_v11_is_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = EvidenceDashboardService(Path(tmp))
            params = {"run_id": "dashboard-run-00000002", "sample": "sample-a", "db": "ptv"}
            with patch.object(ux_dashboard, "EVIDENCE_SERVICE", service):
                ux_dashboard.initialize_evidence_dashboard_state("evidence_pipeline", params)
                state_path = service.evidence_root / "state/dashboard-run-00000002.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state.update({
                    "status": "failed", "official_v1_status": "done",
                    "evidence_v2_status": "failed", "analysis_outcome": "NOT_EVALUABLE",
                })
                state_path.write_text(json.dumps(state), encoding="utf-8")
                summary = ux_dashboard.evidence_status_summary("dashboard-run-00000002")
                result = service.result("dashboard-run-00000002")
            self.assertEqual(summary["official_v1_status"], "done")
            self.assertEqual(summary["evidence_v2_status"], "failed")
            self.assertEqual(summary["experimental_analysis_outcome"], "NOT_EVALUABLE")
            self.assertIn("não foi concluída", summary["experimental_warning"])
            self.assertFalse(result["valid_alpha2"])
            self.assertIn("Relatório anterior: done", result["official_v1"])
            self.assertIn("NOT_EVALUABLE", result["experimental_warning"])


if __name__ == "__main__":
    unittest.main()
