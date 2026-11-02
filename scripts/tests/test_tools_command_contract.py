"""Contracts for the public tools, without executing any analysis command."""
import sys
import gzip
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from dashboard.jobs import build_command
from dashboard import jobs


class ToolsCommandContractTests(unittest.TestCase):
    def test_complementary_analysis_rejects_search_method_before_launch(self):
        with self.assertRaisesRegex(ValueError, "Método"):
            build_command("advanced_analysis", {"sample": "fixture", "method": "blast"})

    def test_complementary_analysis_preserves_supported_method(self):
        command, _ = build_command("advanced_analysis", {"sample": "fixture", "method": "auto"})
        self.assertEqual(command[command.index("--method") + 1], "auto")
        self.assertIn("scripts/experimental/advanced_analysis/run.sh", command)

    def test_standalone_assembly_preserves_explicit_choice(self):
        for assembler in ("velvet", "spades", "metaspades"):
            with self.subTest(assembler=assembler):
                command, _ = build_command("assembly_only", {"sample": "fixture", "assembler": assembler, "kmer": "31"})
                self.assertEqual(command[command.index("--assembler") + 1], assembler)
                self.assertEqual(command[command.index("--kmer") + 1], "31")

    def test_standalone_threads_are_explicit_and_validated(self):
        _, env = build_command("assembly_only", {"sample": "fixture", "threads": "3"})
        self.assertEqual(env["THREADS"], "3")
        with self.assertRaisesRegex(ValueError, "Threads"):
            build_command("assembly_only", {"sample": "fixture", "threads": "0"})

    def test_standalone_snapshot_keeps_own_summary_without_other_analysis_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "data/assemblies/fixture_assembly/contigs.fa": ">artificial\nACGT\n",
                "results/assemblies/fixture/assembly_only_summary.md": "own assembly summary",
                "results/reports/fixture_summary.md": "unrelated prior report",
                "results/phylogeny/fixture_k31/tree.nwk": "unrelated prior tree",
            }
            for name, contents in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents)
            with patch.object(jobs, "get_repo_root", return_value=root), patch.object(jobs, "get_runs_dir", return_value=root / "results/runs"):
                run = Path(jobs.snapshot_run_artifacts({"run_id": "assembly-fixture-0001", "sample": "fixture", "action": "assembly_only"}))
            self.assertEqual((run / "report.md").read_text(), "own assembly summary")
            self.assertEqual(set(json.loads((run / "manifest.json").read_text())["artifacts"]), {"metadata.json", "assembly_contigs.fa", "report.md"})


@unittest.skipUnless(shutil.which("bash"), "Bash is required for the controlled script contract")
class StandaloneAssemblyScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("experimental/assembly_only/run.sh", "lib/common.sh", "lib/input_validation.py"):
            target = self.root / "scripts" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "scripts" / name, target)
        wrapper = self.root / "scripts/pipeline/assemblers/spades.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('#!/usr/bin/env bash\nset -eu\nprintf "%s" "$2" > "$ASSEMBLY_DIR/received_threads"\nmkdir -p "$ASSEMBLY_DIR/${1}_spades"\nif [[ "${CONTROLLED_MISSING_OUTPUT:-}" != 1 ]]; then printf ">artificial\\nACGT\\n" > "$ASSEMBLY_DIR/${1}_spades/contigs.fasta"; fi\n')
        wrapper.chmod(0o755)

    def reads(self, suffix):
        raw = self.root / "data/raw"
        raw.mkdir(parents=True, exist_ok=True)
        for mate in (1, 2):
            target = raw / f"fixture_R{mate}{suffix}"
            payload = f"@artificial/{mate}\nACGT\n+\nIIII\n".encode()
            target.write_bytes(gzip.compress(payload) if suffix.endswith(".gz") else payload)

    def execute(self, **extra):
        return subprocess.run(["bash", str(self.root / "scripts/experimental/assembly_only/run.sh"), "--sample", "fixture", "--assembler", "spades"],
                              env={**os.environ, "THREADS": "3", **extra}, capture_output=True, text=True, timeout=20)

    def test_imported_read_formats_produce_own_summary_with_controlled_assembler(self):
        for suffix in (".fastq.gz", ".fastq", ".fq.gz", ".fq"):
            with self.subTest(suffix=suffix):
                self.reads(suffix)
                result = self.execute()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.root / "data/assemblies/received_threads").read_text(), "3")
                self.assertIn("3", (self.root / "results/assemblies/fixture/assembly_only_summary.md").read_text())
                self.assertEqual((self.root / "data/assemblies/fixture_assembly/contigs.fa").read_text(), ">artificial\nACGT\n")
                for path in (self.root / "data/raw").iterdir():
                    path.unlink()

    def test_missing_reads_fail_before_assembly(self):
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FASTQs", result.stderr)
        self.assertFalse((self.root / "data/assemblies/received_threads").exists())

    def test_missing_assembler_output_does_not_create_success_report(self):
        self.reads(".fastq.gz")
        result = self.execute(CONTROLLED_MISSING_OUTPUT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "results/assemblies/fixture/assembly_only_summary.md").exists())


if __name__ == "__main__":
    unittest.main()
