import importlib.util
import json
import os
import tempfile
import time
import unittest
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "contig_comparison", ROOT / "scripts" / "experimental" / "contig_comparison" / "contig_comparison.py"
)
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)

JOBS_SPEC = importlib.util.spec_from_file_location(
    "ux_dashboard", ROOT / "scripts" / "ux_dashboard.py"
)
dashboard = importlib.util.module_from_spec(JOBS_SPEC)
JOBS_SPEC.loader.exec_module(dashboard)


class ContigComparisonTests(unittest.TestCase):
    def _committed_run(self, root: Path, run_id="run-source-0001", sample="sample-a") -> Path:
        directory = root / "results/runs" / run_id
        directory.mkdir(parents=True)
        metadata = directory / "metadata.json"
        metadata.write_text(json.dumps({"run_id": run_id, "sample": sample, "status": "done"}), encoding="utf-8")
        fasta = directory / "assembly_contigs.fa"
        fasta.write_text(">contig-a\nACGTACGTACGT\n", encoding="utf-8")
        manifest = {
            "schema_version": "1.0", "run_id": run_id, "sample": sample,
            "artifacts": {
                "metadata.json": {
                    "size": metadata.stat().st_size,
                    "sha256": comparison.sha256_file(metadata),
                },
                "assembly_contigs.fa": {
                    "size": fasta.stat().st_size,
                    "sha256": comparison.sha256_file(fasta),
                }
            },
        }
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (directory / "SUCCESS.json").write_text(json.dumps({
            "schema_version": "1.0", "id": run_id, "status": "done", "manifest": "manifest.json",
            "manifest_sha256": comparison.sha256_file(manifest_path),
        }), encoding="utf-8")
        return directory

    def _committed_comparison(self, root: Path, comparison_id="comparison-0001") -> Path:
        directory = root / "results/contig_comparisons" / comparison_id
        directory.mkdir(parents=True)
        for name in sorted(comparison.COMPARISON_ARTIFACTS):
            (directory / name).write_text("{}\n", encoding="utf-8")
        manifest = {
            "schema_version": "1.0", "comparison_id": comparison_id,
            "status": "done", "artifacts": {
                name: {
                    "size": (directory / name).stat().st_size,
                    "sha256": comparison.sha256_file(directory / name),
                }
                for name in sorted(comparison.COMPARISON_ARTIFACTS)
            },
        }
        manifest_path = directory / "comparison_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (directory / "SUCCESS.json").write_text(json.dumps({
            "schema_version": "1.0", "id": comparison_id,
            "comparison_id": comparison_id, "status": "done",
            "manifest": "comparison_manifest.json",
            "manifest_sha256": comparison.sha256_file(manifest_path),
        }), encoding="utf-8")
        return directory

    def _committed_panel(self, root: Path, panel_id="panel-test", count=6) -> tuple[Path, dict[str, str]]:
        directory = root / "results/evidence/panels" / panel_id
        (directory / "blast").mkdir(parents=True)
        (directory / "bowtie2").mkdir()
        categories = sorted(comparison.REQUIRED_CATEGORIES)
        sequences = {
            f"subject-{index:03d}": "ACGT" * (index + 3)
            for index in range(count)
        }
        (directory / "panel.fa").write_text("".join(
            f">{identifier}\n{sequence}\n" for identifier, sequence in sequences.items()
        ), encoding="utf-8")
        (directory / "labels.tsv").write_text(
            "sseqid\tcategory\n" + "".join(
                f"{identifier}\t{categories[index % len(categories)]}\n"
                for index, identifier in enumerate(sequences)
            ), encoding="utf-8",
        )
        for extension in ("nhr", "nin", "nsq"):
            (directory / "blast" / f"panel.{extension}").write_bytes(extension.encode())
        for extension in ("1", "2", "3", "4", "rev.1", "rev.2"):
            (directory / "bowtie2" / f"panel.{extension}.bt2").write_bytes(extension.encode())
        files = {
            path.relative_to(directory).as_posix(): {
                "size": path.stat().st_size, "sha256": comparison.sha256_file(path),
            }
            for path in directory.rglob("*") if path.is_file()
        }
        manifest = {
            "schema_version": "2.0", "panel_id": panel_id,
            "sequence_count": len(sequences), "categories": categories,
            "constructors": {}, "files": files,
        }
        manifest_path = directory / "panel_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (directory / "SUCCESS.json").write_text(json.dumps({
            "panel_id": panel_id, "status": "done", "manifest": "panel_manifest.json",
            "manifest_sha256": comparison.sha256_file(manifest_path),
        }), encoding="utf-8")
        return directory, sequences

    def test_source_requires_success_and_manifest_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = self._committed_run(root)
            source, fasta = comparison.resolve_source(root, "run", directory.name, "sample-a")
            self.assertEqual(source["contigs_source_run"], directory.name)
            self.assertEqual(source["sequence_count"], 1)
            self.assertEqual(fasta.name, "assembly_contigs.fa")

            (directory / "SUCCESS.json").unlink()
            with self.assertRaisesRegex(ValueError, "SUCCESS"):
                comparison.resolve_source(root, "run", directory.name, "sample-a")

    def test_source_rejects_legacy_artifact_list_and_modified_fasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = self._committed_run(root)
            manifest_path = directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"] = list(manifest["artifacts"])
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            success_path = directory / "SUCCESS.json"
            success = json.loads(success_path.read_text(encoding="utf-8"))
            success["manifest_sha256"] = comparison.sha256_file(manifest_path)
            success_path.write_text(json.dumps(success), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "size e sha256"):
                comparison.resolve_source(root, "run", directory.name, "sample-a")

            directory = self._committed_run(root, "run-source-0002")
            (directory / "assembly_contigs.fa").write_text(">contig-a\nAAAA\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "size/hash"):
                comparison.resolve_source(root, "run", directory.name, "sample-a")

    def test_comparison_validator_rejects_incomplete_extra_and_wrong_identity(self):
        mutations = ("missing", "extra", "identity")
        for index, mutation in enumerate(mutations, start=1):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                identifier = f"comparison-{index:04d}"
                directory = self._committed_comparison(root, identifier)
                manifest_path = directory / "comparison_manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if mutation == "missing":
                    manifest["artifacts"].pop("hits.tsv")
                    (directory / "hits.tsv").unlink()
                elif mutation == "extra":
                    (directory / "unexpected.txt").write_text("unexpected", encoding="utf-8")
                    manifest["artifacts"]["unexpected.txt"] = {
                        "size": 10, "sha256": comparison.sha256_file(directory / "unexpected.txt"),
                    }
                else:
                    manifest["comparison_id"] = "comparison-other"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                success_path = directory / "SUCCESS.json"
                success = json.loads(success_path.read_text(encoding="utf-8"))
                success["manifest_sha256"] = comparison.sha256_file(manifest_path)
                success_path.write_text(json.dumps(success), encoding="utf-8")
                with self.assertRaises(ValueError):
                    comparison.validate_comparison(directory)

    def test_panel_rejects_tampering_missing_index_and_internal_symlink(self):
        for mutation in ("tampered", "missing", "symlink"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                directory, sequences = self._committed_panel(root)
                if mutation == "tampered":
                    (directory / "panel.fa").write_text(">changed\nAAAA\n", encoding="utf-8")
                elif mutation == "missing":
                    (directory / "blast/panel.nsq").unlink()
                else:
                    target = root / "outside.nsq"
                    target.write_bytes(b"outside")
                    link = directory / "blast/panel.nsq"
                    link.unlink()
                    try:
                        link.symlink_to(target)
                    except OSError as exc:
                        self.skipTest(f"symlink indisponivel: {exc}")
                with patch.object(comparison.subprocess, "run"), patch.object(
                    comparison, "_blast_database_sequences", return_value=sequences,
                ):
                    with self.assertRaises(ValueError):
                        comparison._panel_reference(root, "panel-test")

    def test_panel_limit_is_raised_to_cover_every_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._committed_run(root)
            captured = []

            def fake_run(command, **_kwargs):
                captured.append(command)
                output = Path(command[command.index("-out") + 1])
                output.write_text("", encoding="utf-8")
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            reference = {
                "reference_kind": "competitive_panel", "reference_database": "panel-large",
                "subject_count": 75, "reference_fasta": "panel.fa",
            }
            with patch.object(comparison, "_panel_reference", return_value=(reference, root / "panel")), patch.object(
                comparison, "_tool", return_value={"command": "blastn", "executable": "blastn", "version": "fixture"},
            ), patch.object(comparison.subprocess, "run", side_effect=fake_run):
                final = comparison.execute(Namespace(
                    repo_root=root, comparison_id="comparison-panel-0001", sample="sample-a",
                    source_type="run", source_id="run-source-0001", reference_kind="panel",
                    database="panel-large", db_query="", ncbi_db="nucleotide", blast_task="blastn",
                    word_size=11, evalue=1e-5, max_target_seqs=50, threads=1,
                ))
            command = captured[0]
            self.assertEqual(command[command.index("-max_target_seqs") + 1], "75")
            parameters = json.loads((final / "blast_parameters.json").read_text(encoding="utf-8"))
            self.assertEqual(parameters["requested_max_target_seqs"], 50)
            self.assertEqual(parameters["effective_max_target_seqs"], 75)
            self.assertEqual(parameters["panel_subject_count"], 75)

    def test_custom_database_preparation_and_blast_are_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._committed_run(root, "run-source-0001", "sample-a")
            self._committed_run(root, "run-source-0002", "sample-b")
            phases = []
            current_query = {"value": None}

            def fake_database(_root, _database, query, _ncbi):
                phases.append(("prepare", query))
                current_query["value"] = query
                time.sleep(0.03)
                return ({
                    "reference_kind": "database", "reference_database": "custom",
                    "reference_fasta": "data/ref/custom.fa", "reference_fasta_sha256": query,
                    "blast_prefix": "blastdb/custom", "index_files": {},
                }, root / "blastdb/custom")

            def fake_run(command, **_kwargs):
                output = Path(command[command.index("-out") + 1])
                expected = "query-a" if "custom-a" in output.parent.name else "query-b"
                phases.append(("blast", current_query["value"]))
                self.assertEqual(current_query["value"], expected)
                time.sleep(0.03)
                output.write_text("", encoding="utf-8")
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            def run(identifier, sample, source_id, query):
                return comparison.execute(Namespace(
                    repo_root=root, comparison_id=identifier, sample=sample,
                    source_type="run", source_id=source_id, reference_kind="database",
                    database="custom", db_query=query, ncbi_db="nucleotide", blast_task="blastn",
                    word_size=11, evalue=1e-5, max_target_seqs=50, threads=1,
                ))

            with patch.object(comparison, "_database_reference", side_effect=fake_database), patch.object(
                comparison, "_tool", return_value={"command": "blastn", "executable": "blastn", "version": "fixture"},
            ), patch.object(comparison.subprocess, "run", side_effect=fake_run):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [
                        pool.submit(run, "comparison-custom-a", "sample-a", "run-source-0001", "query-a"),
                        pool.submit(run, "comparison-custom-b", "sample-b", "run-source-0002", "query-b"),
                    ]
                    for future in futures:
                        future.result()
            self.assertIn(phases, [
                [("prepare", "query-a"), ("blast", "query-a"), ("prepare", "query-b"), ("blast", "query-b")],
                [("prepare", "query-b"), ("blast", "query-b"), ("prepare", "query-a"), ("blast", "query-a")],
            ])

    def test_cancellation_is_terminal_and_staging_safe_across_restart(self):
        for index, status in enumerate(("preparing_database", "running_blast"), start=1):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                identifier = f"comparison-cancel-{index}"
                staging = root / "results/contig_comparisons/.staging" / identifier
                staging.mkdir(parents=True)
                comparison._state(staging, identifier, status, emit=False)
                (staging / "partial.tmp").write_text("partial", encoding="utf-8")
                record = comparison.finalize_contig_comparison_cancellation(root, identifier, "cancelled by test")
                self.assertEqual(record["status"], "cancelled")
                self.assertTrue(record["staging_cleared"])
                self.assertFalse(staging.exists())
                quarantined = root / "results/contig_comparisons/.cancelled" / identifier
                state = json.loads((quarantined / "run_state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["status"], "cancelled")
                # A fresh reader sees no resumable/successful comparison and retains terminal state.
                self.assertEqual(comparison.list_comparisons(root), [])
                persisted = json.loads((root / "results/contig_comparisons/state" / f"{identifier}.json").read_text(encoding="utf-8"))
                self.assertEqual(persisted["status"], "cancelled")

    def test_staging_and_orphan_fasta_are_never_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._committed_run(root)
            partial = root / "results/runs/.staging/run-partial-0001"
            partial.mkdir(parents=True)
            (partial / "assembly_contigs.fa").write_text(">x\nACGT\n", encoding="utf-8")
            orphan = root / "results/runs/run-orphan-0001"
            orphan.mkdir()
            (orphan / "assembly_contigs.fa").write_text(">x\nACGT\n", encoding="utf-8")
            sources = comparison.list_sources(root)
            self.assertEqual([item["source_id"] for item in sources], ["run-source-0001"])

    def test_local_fasta_import_copies_validates_and_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_file = root / "input.fa"
            source_file.write_text(">short\nACGTNN\n", encoding="utf-8")
            result = comparison.import_local_fasta(
                root, source_file, "sample-a", "arquivo fornecido pelo usuario",
                "local-source-0001",
            )
            final = root / "results/contig_sources/local-source-0001"
            self.assertEqual(result["sequence_count"], 1)
            self.assertTrue((final / "SUCCESS.json").is_file())
            self.assertFalse((final / "contigs.fasta").is_symlink())
            self.assertEqual(comparison.list_sources(root)[0]["source_type"], "local")

    def test_local_fasta_requires_declared_origin_and_nucleotides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fasta = root / "bad.fa"
            fasta.write_text(">protein\nMPEP\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nucleotidicos"):
                comparison.import_local_fasta(root, fasta, "sample-a", "origem", "local-source-0001")
            fasta.write_text(">ok\nACGT\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "origem declarada"):
                comparison.import_local_fasta(root, fasta, "sample-a", "", "local-source-0002")

    def test_dashboard_command_is_narrow_and_validates_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._committed_run(root)
            params = {
                "sample": "sample-a", "comparison_id": "comparison-0001",
                "source_type": "run", "source_id": "run-source-0001", "db": "ptv",
                "blast_task": "blastn-short", "word_size": "7", "evalue": "1e-4",
                "max_target_seqs": "100", "threads": "2",
            }
            with patch.dict(dashboard.build_command.__globals__, {"get_repo_root": lambda: root}):
                command, environment = dashboard.build_command("compare_contigs", params)
            self.assertIn("scripts/experimental/contig_comparison/run.sh", command)
            self.assertNotIn("scripts/pipeline/run.sh", command)
            self.assertFalse(any("evidence" in item.lower() for item in command))
            self.assertEqual(environment, {})

    def test_dashboard_surface_separates_comparison_from_assembly_and_evidence(self):
        html = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "dashboard/js/advanced.js").read_text(encoding="utf-8")
        self.assertIn('href="#/advanced"', html)
        self.assertIn("Comparação de contigs", javascript)
        self.assertIn("sem remontagem", javascript)
        self.assertIn("fonte imutável", javascript)
        self.assertIn("/api/experimental/contig-sources", javascript)
        self.assertIn('action: "compare_contigs"', javascript)
        self.assertIn("reference_database", javascript)

    def test_two_comparisons_have_independent_final_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._committed_run(root)

            def fake_database(_root, database, _query, _ncbi):
                return ({
                    "reference_kind": "database", "reference_database": database,
                    "reference_fasta": "data/ref/test.fa", "reference_fasta_sha256": "a",
                    "blast_prefix": "blastdb/test", "index_files": {"blastdb/test.nsq": {}},
                }, root / "blastdb/test")

            def fake_run(command, **kwargs):
                if "-out" in command:
                    output = Path(command[command.index("-out") + 1])
                    output.write_text("contig-a\tref-a\t100\t12\t0\t0\t1\t12\t1\t12\t1e-9\t24\t12\t12\n", encoding="utf-8")
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with patch.object(comparison, "_database_reference", side_effect=fake_database), patch.object(
                comparison, "_tool", return_value={"command": "blastn", "executable": "blastn", "version": "fixture"}
            ), patch.object(comparison.subprocess, "run", side_effect=fake_run):
                for identifier, database in (("comparison-0001", "bank-a"), ("comparison-0002", "bank-b")):
                    comparison.execute(Namespace(
                        repo_root=root, comparison_id=identifier, sample="sample-a",
                        source_type="run", source_id="run-source-0001", reference_kind="database",
                        database=database, db_query="", ncbi_db="nucleotide", blast_task="blastn",
                        word_size=11, evalue=1e-5, max_target_seqs=50, threads=1,
                    ))
            first = root / "results/contig_comparisons/comparison-0001"
            second = root / "results/contig_comparisons/comparison-0002"
            self.assertTrue((first / "SUCCESS.json").is_file())
            self.assertTrue((second / "SUCCESS.json").is_file())
            self.assertEqual(len(comparison.list_comparisons(root)), 2)
            self.assertEqual((root / "results/runs/run-source-0001/assembly_contigs.fa").read_text(), ">contig-a\nACGTACGTACGT\n")

            first_success = (first / "SUCCESS.json").read_bytes()
            with patch.object(comparison, "_database_reference", side_effect=fake_database), patch.object(
                comparison, "_tool", return_value={"command": "blastn", "executable": "blastn", "version": "fixture"}
            ), patch.object(
                comparison.subprocess, "run", side_effect=comparison.subprocess.CalledProcessError(2, ["blastn"])
            ):
                with self.assertRaises(comparison.subprocess.CalledProcessError):
                    comparison.execute(Namespace(
                        repo_root=root, comparison_id="comparison-fail-0003", sample="sample-a",
                        source_type="run", source_id="run-source-0001", reference_kind="database",
                        database="bank-c", db_query="", ncbi_db="nucleotide", blast_task="blastn",
                        word_size=11, evalue=1e-5, max_target_seqs=50, threads=1,
                    ))
            self.assertEqual((first / "SUCCESS.json").read_bytes(), first_success)
            self.assertFalse((root / "results/contig_comparisons/comparison-fail-0003").exists())


if __name__ == "__main__":
    unittest.main()
