"""Data and CLI output can live outside the source tree when requested."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.dashboard import jobs


ROOT = Path(__file__).resolve().parents[2]


def _run(args, env):
    merged = os.environ.copy()
    for key in ("DB", "DB_QUERY", "REF_FASTA", "BLAST_DB", "BOWTIE2_INDEX", "GENEIN_WORK_ROOT"):
        merged.pop(key, None)
    merged.update(env)
    return subprocess.run(args, cwd=ROOT, env=merged, text=True, capture_output=True, check=False)


class ExternalWorkRootTests(unittest.TestCase):
    def test_make_forwards_an_explicit_fasta_and_moves_defaults(self):
        explicit = _run(
            ["make", "-n", "db", "DB=meu_banco", "REF_FASTA=/dados/referencia.fa",
             "BLAST_DB=/dados/blastdb/meu_banco", "BOWTIE2_INDEX=/dados/bowtie2/meu_banco"],
            {"GENEIN_WORK_ROOT": "/tmp/fora-genein"},
        )
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertIn('REF_FASTA="/dados/referencia.fa"', explicit.stdout)
        self.assertIn('BLAST_DB="/dados/blastdb/meu_banco"', explicit.stdout)

        default = _run(["make", "-n", "db", "DB=ptv"], {"GENEIN_WORK_ROOT": "/tmp/fora-genein"})
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertIn('BLAST_DB="/tmp/fora-genein/blastdb/ptv"', default.stdout)
        self.assertIn('BOWTIE2_INDEX="/tmp/fora-genein/bowtie2/ptv"', default.stdout)
        self.assertNotIn("REF_FASTA=", default.stdout)

        inside = _run(["make", "-n", "db", "DB=ptv"], {})
        self.assertIn('BLAST_DB="blastdb/ptv"', inside.stdout)
        self.assertNotIn("REF_FASTA=", inside.stdout)

    def test_make_pipeline_uses_blast_db_from_the_work_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            config = work / "config"
            config.mkdir(parents=True)
            env_file = config / "picornavirus.env"
            env_file.write_text("DB=ptv\nBLAST_DB=/dados/blastdb/ptv\n", encoding="utf-8")
            env_file.chmod(0o644)
            result = _run(
                ["make", "-n", "pipeline", "SAMPLE=demo"],
                {"GENEIN_WORK_ROOT": str(work), "HOME": str(root / "home")},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('BLAST_DB="/dados/blastdb/ptv"', result.stdout)
            self.assertNotIn("blastdb/custom", result.stdout)

    def test_make_pipeline_finds_a_prepared_database_outside_the_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            config = work / "config"
            config.mkdir(parents=True)
            env_file = config / "picornavirus.env"
            env_file.write_text("DB=ptv\n", encoding="utf-8")
            env_file.chmod(0o644)
            manifest = work / "blastdb" / "ptv.db-manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}\n", encoding="utf-8")
            result = _run(
                ["make", "-n", "pipeline", "SAMPLE=demo"],
                {"GENEIN_WORK_ROOT": str(work), "HOME": str(root / "home")},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f'BLAST_DB="{work}/blastdb/ptv"', result.stdout)

    def test_panel_finds_a_prepared_database_outside_the_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            prefix = work / "blastdb" / "ptv"
            manifest = work / "blastdb" / "ptv.db-manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}\n", encoding="utf-8")
            env = os.environ.copy()
            env["GENEIN_WORK_ROOT"] = str(work)
            env["HOME"] = str(root / "home")
            env.pop("GENEIN_CONFIG_FILE", None)
            env.pop("BLAST_DB", None)
            with patch.dict(os.environ, env, clear=True):
                from scripts.dashboard.config import list_db_profiles
                profiles = list_db_profiles()
                ptv = next(item for item in profiles if item["id"] == "ptv")
                self.assertTrue(ptv["prepared"])
                self.assertEqual(ptv["prefix"], str(prefix))
                self.assertFalse(str(ptv["prefix"]).startswith(str(ROOT / "blastdb")))
                _cmd, built = jobs.build_command(
                    "evidence_pipeline",
                    {"sample": "SAMPLE", "db": "ptv", "assembler": "consensus",
                     "host_filter_mode": "none", "run_id": "first-run-00001"},
                )
            self.assertEqual(built["BLAST_DB"], str(prefix))
            self.assertNotEqual(built["BLAST_DB"], str(ROOT / "blastdb" / "ptv"))

    def test_profile_download_uses_the_work_root_without_a_local_fasta(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _run(["make", "db", "DB=ptv"], {"GENEIN_WORK_ROOT": directory})
            text = result.stdout + result.stderr
            self.assertNotIn("FASTA local ausente", text)
            self.assertIn(directory, text)
            self.assertFalse((ROOT / "data" / "ref" / "ptv.fa").exists())
            self.assertTrue((Path(directory) / "tmp" / "db-manager.lock").is_file())


class ExternalHistoryTests(unittest.TestCase):
    def _history(self, output_root):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = SimpleNamespace(evidence_root=root / "absent", inspect_run=lambda _run_id: {})
            env = os.environ.copy()
            if output_root is None:
                env.pop("GENEIN_OUTPUT_ROOT", None)
            else:
                env["GENEIN_OUTPUT_ROOT"] = output_root
            with patch.object(jobs, "get_repo_root", return_value=root), \
                    patch.object(jobs, "get_runs_dir", return_value=root / "runs"), \
                    patch.object(jobs, "EVIDENCE_SERVICE", service), \
                    patch.dict(os.environ, env, clear=True):
                return jobs.list_run_history()

    def test_history_lists_a_cli_receipt_outside_the_source(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            run = parent / "execucao"
            run.mkdir()
            (run / "execution.json").write_text(json.dumps({
                "run_id": "run-externo",
                "status": "completed",
                "started_at": "2026-10-20T12:00:00+00:00",
                "finished_at": "2026-10-20T12:05:00+00:00",
            }), encoding="utf-8")
            history = self._history(str(parent))
            match = [item for item in history if item.get("run_id") == "run-externo"]
            self.assertEqual(len(match), 1)
            self.assertEqual(match[0]["output_root"], str(run))
            self.assertEqual(match[0]["status"], "done")
            self.assertEqual(match[0]["run_dir"], "")
            self.assertEqual(match[0]["sample"], "")

    def test_history_reads_the_sample_from_the_receipt_or_the_command(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            named = parent / "nomeada"
            named.mkdir()
            (named / "execution.json").write_text(json.dumps({
                "run_id": "run-nomeada",
                "sample": "amostra-1",
                "status": "completed",
                "command": ["bash", "run_sample.sh", "--sample", "outra"],
                "finished_at": "2026-10-20T12:05:00+00:00",
            }), encoding="utf-8")
            legacy = parent / "legada"
            legacy.mkdir()
            (legacy / "execution.json").write_text(json.dumps({
                "run_id": "run-legada",
                "status": "completed",
                "command": ["bash", "run_sample.sh", "--sample", "amostra-2", "--threads", "2"],
                "finished_at": "2026-10-20T12:04:00+00:00",
            }), encoding="utf-8")
            history = {item["run_id"]: item for item in self._history(str(parent))}
            self.assertEqual(history["run-nomeada"]["sample"], "amostra-1")
            self.assertEqual(history["run-legada"]["sample"], "amostra-2")

    def test_history_stays_empty_when_the_variable_is_unset(self):
        self.assertEqual(self._history(None), [])


if __name__ == "__main__":
    unittest.main()
