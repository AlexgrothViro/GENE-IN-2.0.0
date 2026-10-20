import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ux_dashboard", ROOT / "scripts" / "ux_dashboard.py")
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class DashboardSecurityTests(unittest.TestCase):
    def test_only_loopback_hosts_are_allowed(self):
        self.assertTrue(dashboard.is_loopback_host("127.0.0.1"))
        self.assertTrue(dashboard.is_loopback_host("localhost"))
        self.assertFalse(dashboard.is_loopback_host("0.0.0.0"))
        self.assertFalse(dashboard.is_loopback_host("192.168.1.10"))

    def test_config_values_are_shell_quoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "picornavirus.env"
            original = dashboard.CONFIG_ENV_PRIMARY
            dashboard.CONFIG_ENV_PRIMARY = target
            try:
                dashboard.save_config_env({"SPADES_PARAMS": "$(touch should_not_run)"})
                content = target.read_text(encoding="utf-8")
                self.assertIn("'$(touch should_not_run)'", content)
            finally:
                dashboard.CONFIG_ENV_PRIMARY = original

        with self.assertRaises(ValueError):
            dashboard.validate_config_updates({"BIND_HOST": "0.0.0.0"})

    def test_upload_rejects_traversal_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = dashboard.REPO_ROOT
            dashboard.REPO_ROOT = Path(tmp)
            r1 = b"@read/1\nACGT\n+\nIIII\n"
            r2 = b"@read/2\nTGCA\n+\nIIII\n"
            try:
                with self.assertRaises(ValueError):
                    dashboard.import_uploaded_files("../escape", "r1.fastq", r1, "r2.fastq", r2)
                dashboard.import_uploaded_files("safe", "r1.fastq", r1, "r2.fastq", r2)
                with self.assertRaises(FileExistsError):
                    dashboard.import_uploaded_files("safe", "r1.fastq", r1, "r2.fastq", r2)
            finally:
                dashboard.REPO_ROOT = original

    def test_pipeline_requires_explicit_database_selection(self):
        with self.assertRaisesRegex(ValueError, "explicitamente"):
            dashboard.build_command("pipeline", {"sample": "safe", "assembler": "spades"})
        command, environment = dashboard.build_command(
            "pipeline", {"sample": "safe", "assembler": "spades", "db": "ptv"}
        )
        self.assertIn("scripts/pipeline/run.sh", command)
        self.assertEqual(
            command,
            [
                "scripts/pipeline/run.sh",
                "--sample", "safe",
                "--assembler", "spades",
                "--analysis-profile", "default",
            ],
        )
        self.assertFalse(any(item.startswith("SAMPLE=") for item in command))
        self.assertEqual(environment["DB"], "ptv")
        self.assertEqual(environment["HOST_FILTER_ENABLED"], "false")

    def test_pipeline_propagates_custom_database_provenance(self):
        command, environment = dashboard.build_command(
            "pipeline",
            {
                "sample": "zikaer",
                "assembler": "velvet",
                "db": "custom",
                "db_query": "Orthoflavivirus zikaense",
                "ncbi_db": "nucleotide",
            },
        )
        self.assertEqual(command[1:3], ["--sample", "zikaer"])
        self.assertEqual(environment["DB"], "custom")
        self.assertEqual(
            environment["DB_QUERY"], "Orthoflavivirus zikaense"
        )
        self.assertEqual(environment["NCBI_DB"], "nucleotide")

    def test_pipeline_recovers_custom_query_from_database_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / "config").mkdir()
            (repo_root / "config/analysis_profiles.json").write_bytes(
                (ROOT / "config/analysis_profiles.json").read_bytes())
            metadata_dir = repo_root / "db" / "custom"
            metadata_dir.mkdir(parents=True)
            (metadata_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "db": "custom",
                        "db_query": "Orthoflavivirus zikaense",
                        "ncbi_db": "nucleotide",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                dashboard.build_command.__globals__,
                {"REPO_ROOT": repo_root},
            ):
                _, environment = dashboard.build_command(
                    "pipeline",
                    {
                        "sample": "zikaer",
                        "assembler": "velvet",
                        "db": "custom",
                    },
                )
        self.assertEqual(environment["DB_QUERY"], "Orthoflavivirus zikaense")
        self.assertEqual(environment["NCBI_DB"], "nucleotide")

    def test_custom_database_without_query_or_metadata_fails_closed(self):
        # O banco customizado nunca deve ser resolvido implicitamente a partir de
        # estado local nao versionado: sem query explicita e sem db/custom/metadata.json
        # a construcao do comando falha fechada.
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                dashboard.build_command.__globals__,
                {"REPO_ROOT": Path(tmp)},
            ):
                with self.assertRaisesRegex(ValueError, "exige uma query NCBI"):
                    dashboard.build_command(
                        "pipeline",
                        {"sample": "safe", "assembler": "spades", "db": "custom"},
                    )

    def test_unknown_host_selection_is_an_explicit_safe_opt_out(self):
        host_environment = dashboard.host_env_from_params(
            {"host_filter_mode": "none"}
        )
        self.assertNotEqual(host_environment.get("HOST_FILTER_MODE"), "none")

        _, environment = dashboard.build_command(
            "pipeline",
            {
                "sample": "zika-unknown-host",
                "assembler": "spades",
                "db": "custom",
                "db_query": "Orthoflavivirus zikaense",
                "host_filter_mode": "none",
            },
        )
        self.assertEqual(environment["HOST_FILTER_ENABLED"], "false")
        self.assertNotIn("HOST_NAME", environment)
        self.assertNotIn("HOST_INDEX_PREFIX", environment)

    def test_sus_scrofa_filter_is_opt_in_and_resolves_its_index(self):
        _, environment = dashboard.build_command(
            "pipeline",
            {
                "sample": "safe",
                "assembler": "spades",
                "db": "custom",
                "db_query": "Orthoflavivirus zikaense",
                "host_filter_mode": "sus_scrofa",
            },
        )
        self.assertEqual(environment["HOST_FILTER_ENABLED"], "true")
        self.assertEqual(environment["HOST_NAME"], "Sus scrofa")
        self.assertTrue(
            environment["HOST_INDEX_PREFIX"].endswith("ref/host/sus_scrofa_bt2")
            or environment["HOST_INDEX_PREFIX"].endswith(r"ref\host\sus_scrofa_bt2")
        )

    def test_host_filter_rejects_unknown_modes_and_incomplete_custom_index(self):
        with self.assertRaisesRegex(ValueError, "Modo de filtro"):
            dashboard.host_env_from_params({"host_filter_mode": "strict"})
        with self.assertRaisesRegex(ValueError, "exige nome e prefixo"):
            dashboard.build_command(
                "pipeline",
                {
                    "sample": "safe",
                    "assembler": "spades",
                    "db": "custom",
                    "db_query": "Orthoflavivirus zikaense",
                    "host_filter_mode": "custom",
                },
            )

    def test_auxiliary_dashboard_actions_have_executable_commands(self):
        check_command, _ = dashboard.build_command("check_env", {})
        demo_command, _ = dashboard.build_command("demo", {})
        db_command, _ = dashboard.build_command("build_db", {"db": "ptv"})
        target_command, _ = dashboard.build_command("build_db", {"target": "teschovirus_a"})
        custom_command, custom_env = dashboard.build_command(
            "build_db", {"query": '"Zika virus"[Organism]'}
        )
        named_custom_command, named_custom_env = dashboard.build_command(
            "build_db", {"db": "custom", "db_query": '"Orbivirus"[Organism]'}
        )
        taxid_command, taxid_env = dashboard.build_command("build_db", {"taxid": "12087"})
        assembly_command, _ = dashboard.build_command(
            "assembly_only", {"sample": "safe", "assembler": "spades"}
        )
        self.assertEqual(check_command, ["bash", "scripts/ops/check_env.sh"])
        self.assertEqual(demo_command, ["make", "demo"])
        self.assertIn("make", db_command)
        self.assertIn("DB=ptv", target_command)
        self.assertEqual(custom_command, ["bash", "scripts/ops/db_manager.sh", "setup"])
        self.assertEqual(custom_env["DB"], "custom")
        self.assertIn("Zika virus", custom_env["DB_QUERY"])
        self.assertEqual(named_custom_command, custom_command)
        self.assertEqual(named_custom_env["DB"], "custom")
        self.assertIn("Orbivirus", named_custom_env["DB_QUERY"])
        self.assertEqual(taxid_command, custom_command)
        self.assertEqual(taxid_env["DB_QUERY"], "txid12087[Organism:exp]")
        self.assertIn("scripts/experimental/assembly_only/run.sh", assembly_command)
        with self.assertRaisesRegex(ValueError, "query NCBI"):
            dashboard.build_command("build_db", {"db": "custom"})
        with self.assertRaisesRegex(ValueError, "numerico"):
            dashboard.build_command("build_db", {"taxid": "abc"})

    def test_import_sample_accepts_local_fastq_paths(self):
        with self.assertRaisesRegex(ValueError, "Acao desconhecida"):
            dashboard.build_command("sample_add", {})

        with tempfile.TemporaryDirectory() as tmp:
            r1 = Path(tmp) / "safe_R1.fastq"
            r2 = Path(tmp) / "safe_R2.fastq"
            payload = "@r\nACGT\n+\nIIII\n"
            r1.write_text(payload, encoding="utf-8")
            r2.write_text(payload, encoding="utf-8")
            command, _ = dashboard.build_command(
                "import_sample",
                {"sample": "safe", "r1": str(r1), "r2": str(r2), "copy": True},
            )
            self.assertEqual(command[0], "make")
            self.assertIn("sample-add", command)
            self.assertTrue(any(item.startswith("ID=safe") for item in command))
            self.assertTrue(any(item.startswith("R1=") and "safe_R1.fastq" in item for item in command))
            self.assertTrue(any(item.startswith("R2=") and "safe_R2.fastq" in item for item in command))
            self.assertIn("COPY=1", command)
            if os.name == "nt":
                r1_arg = next(item for item in command if item.startswith("R1="))
                self.assertTrue(r1_arg.startswith("R1=/mnt/"), r1_arg)
            with self.assertRaisesRegex(ValueError, "nao encontrado"):
                dashboard.build_command(
                    "import_sample",
                    {"sample": "safe", "r1": str(r1), "r2": str(Path(tmp) / "missing_R2.fastq")},
                )

    def test_evidence_requires_database_and_defaults_to_no_host_filter(self):
        with self.assertRaisesRegex(ValueError, "explicitamente"):
            dashboard.build_command(
                "evidence_pipeline",
                {"sample": "safe", "assembler": "spades"},
            )
        command, environment = dashboard.build_command(
            "evidence_pipeline",
            {"sample": "safe", "assembler": "spades", "db": "ptv"},
        )
        self.assertIn("scripts/pipeline/run.sh", command)
        self.assertEqual(environment["DB"], "ptv")
        self.assertEqual(environment["HOST_FILTER_ENABLED"], "false")

    def test_evidence_batch_requires_database_and_accepts_explicit_host_filter(self):
        with patch.object(
            dashboard.EVIDENCE_SERVICE,
            "manifest_export",
            return_value=ROOT / "manifest.tsv",
        ), patch.object(
            dashboard,
            "validate_host_index",
            return_value={"valid": True, "message": "fixture"},
        ):
            with self.assertRaisesRegex(ValueError, "explicitamente"):
                dashboard.build_command("evidence_batch", {"manifest_id": "batch-safe"})
            command, environment = dashboard.build_command(
                "evidence_batch",
                {
                    "manifest_id": "batch-safe",
                    "target": "ptv",
                    "host_filter_mode": "custom",
                    "host_name": "Bos taurus",
                    "host_index_prefix": "ref/host/bos_taurus_bt2",
                },
            )
        self.assertIn("scripts/evidence/run_batch.sh", command)
        self.assertEqual(environment["DB"], "ptv")
        self.assertEqual(environment["HOST_FILTER_ENABLED"], "true")
        self.assertEqual(environment["HOST_NAME"], "Bos taurus")
        self.assertEqual(environment["HOST_INDEX_PREFIX"], "ref/host/bos_taurus_bt2")

    def test_evidence_commands_match_the_shell_parsers(self):
        command, environment = dashboard.build_command(
            "evidence_pipeline",
            {
                "sample": "safe",
                "assembler": "metaspades",
                "db": "custom",
                "db_query": "Orthoflavivirus zikaense",
                "run_id": "run-safe-0001",
                "analysis_profile": "default",
            },
        )
        self.assertEqual(
            command,
            [
                "scripts/pipeline/run.sh",
                "--sample", "safe",
                "--assembler", "metaspades",
                "--analysis-profile", "default",
                "--evidence-v2",
                "--evidence-profiles", "config/evidence_profiles.json",
                "--r1", str(dashboard.REPO_ROOT / "data/raw/safe_R1.fastq.gz"),
                "--r2", str(dashboard.REPO_ROOT / "data/raw/safe_R2.fastq.gz"),
            ],
        )
        self.assertEqual(environment["EVIDENCE_RUN_ID"], "run-safe-0001")
        self.assertNotIn("--run-id=run-safe-0001", command)
        self.assertFalse(any(item.startswith("--db") for item in command))

        with patch.object(
            dashboard.EVIDENCE_SERVICE,
            "manifest_export",
            return_value=ROOT / "manifest.tsv",
        ):
            batch_command, _ = dashboard.build_command(
                "evidence_batch",
                {
                    "manifest_id": "batch-safe",
                    "target": "custom",
                    "db_query": "Orthoflavivirus zikaense",
                    "run_id": "batch-run-0001",
                },
            )
        self.assertEqual(
            batch_command,
            [
                "scripts/evidence/run_batch.sh",
                "--batch-manifest", str(ROOT / "manifest.tsv"),
                "--run-id", "batch-run-0001",
                "--profiles", "config/evidence_profiles.json",
            ],
        )

    def test_dashboard_contract_has_no_silent_host_or_scientific_authority_label(self):
        html = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
        operational = (ROOT / "dashboard/js/operational.js").read_text(encoding="utf-8")
        advanced = (ROOT / "dashboard/js/advanced.js").read_text(encoding="utf-8")
        self.assertLess(
            operational.index('value: "none", text: "Sem filtro de hospedeiro"'),
            operational.index('value: "sus_scrofa", text: "Sus scrofa — exige índice preparado separadamente"'),
        )
        self.assertNotIn("Configuração padrão", operational)
        self.assertNotIn("Validação Científica", html)
        self.assertNotIn("Validação Científica", operational)
        self.assertIn("controles de integridade e rastreabilidade", advanced)
        self.assertIn("Artefatos validados", (ROOT / "dashboard/js/analytics.js").read_text(encoding="utf-8"))

    def test_evidence_history_uses_canonical_state_once_and_sorts_by_timestamp(self):
        class InspectionService:
            @staticmethod
            def inspect_run(_run_id):
                return {
                    "status": "INCOMPLETE", "valid_alpha2": False,
                    "complete": False, "message": "incompleto",
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "results/runs"
            legacy = runs_dir / "legacy"
            evidence_snapshot = runs_dir / "evidence-snapshot"
            legacy.mkdir(parents=True)
            evidence_snapshot.mkdir()
            (legacy / "run.json").write_text(json.dumps({
                "action": "pipeline", "sample": "legacy",
                "end_epoch": 10, "start": "2026-01-01T00:00:00+00:00",
            }), encoding="utf-8")
            (evidence_snapshot / "run.json").write_text(json.dumps({
                "action": "evidence_pipeline", "sample": "sample-a",
                "end_epoch": 20,
            }), encoding="utf-8")
            state_dir = root / "results/evidence/state"
            state_dir.mkdir(parents=True)
            (state_dir / "run-v2.json").write_text(json.dumps({
                "run_id": "run-v2", "action": "evidence_single",
                "sample_ids": ["sample-a"], "status": "failed",
                "evidence_v2_status": "failed", "official_v1_status": "done",
                "created_at": "2026-01-02T00:00:00+00:00",
                "finished_at": "2026-01-02T01:00:00+00:00",
                "failure_message": "falha sintética",
            }), encoding="utf-8")
            with (
                patch.object(dashboard, "REPO_ROOT", root),
                patch.object(dashboard, "RUNS_DIR", runs_dir),
                patch.object(dashboard, "EVIDENCE_SERVICE", InspectionService()),
            ):
                history = dashboard.list_run_history()
            self.assertEqual(len(history), 2)
            self.assertTrue(history[0]["evidence_v2"])
            self.assertEqual(history[0]["run_id"], "run-v2")
            self.assertEqual(history[1]["sample"], "legacy")

    def test_legacy_history_is_read_only_and_remains_ineligible_as_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "results/runs"
            run_dir = runs_dir / "run-zikaer"
            run_dir.mkdir(parents=True)
            (run_dir / "metadata.json").write_text(json.dumps({
                "action": "pipeline", "sample": "zikaer", "run_id": "run-zikaer",
                "status": "done", "finished_at": "2026-07-30T16:37:34-03:00",
            }), encoding="utf-8")
            (root / "results/blast").mkdir(parents=True)
            (root / "results/blast/zikaer_k31_vs_db.tsv").write_text("raw\n", encoding="utf-8")
            (root / "results/blast/zikaer_labeled_hits.tsv").write_text("labeled\n", encoding="utf-8")
            (root / "results/blast/zikaer_adj_identity.tsv").write_text("adjusted\n", encoding="utf-8")
            (root / "results/blast/zikaer_hit_contigs.fasta").write_text(">hit\nACGT\n", encoding="utf-8")
            (root / "results/reports").mkdir(parents=True)
            (root / "results/reports/zikaer_summary.md").write_text("report\n", encoding="utf-8")
            (root / "data/assemblies/zikaer_assembly").mkdir(parents=True)
            (root / "data/assemblies/zikaer_assembly/contigs.fa").write_text(">contig\nACGT\n", encoding="utf-8")
            (root / "logs").mkdir(parents=True)
            (root / "logs/ux_run-zikaer.log").write_text("log\n", encoding="utf-8")
            history_globals = dashboard.list_run_history.__globals__
            resolve_globals = dashboard.resolve_history_file.__globals__
            with patch.dict(
                history_globals,
                {
                    "get_repo_root": lambda: root,
                    "get_runs_dir": lambda: runs_dir,
                    "EVIDENCE_SERVICE": type("Service", (), {"evidence_root": root / "results/evidence"})(),
                },
            ), patch.dict(resolve_globals, {"get_runs_dir": lambda: runs_dir}):
                history = dashboard.list_run_history()
                self.assertEqual(history[0]["run_dir"], "run-zikaer")
                self.assertFalse((run_dir / "SUCCESS.json").exists())
                self.assertEqual(history[0]["paths"], {})
                self.assertIsNone(dashboard.resolve_history_file("run-zikaer", "assembly_contigs_fasta"))

    def test_duplicate_query_values_are_rejected(self):
        self.assertEqual(dashboard.query_one({"run": ["ok"]}, "run"), "ok")
        with self.assertRaisesRegex(ValueError, "duplicado"):
            dashboard.query_one({"run": ["a", "..\\secret"]}, "run")

    def test_operational_snapshot_is_not_evidence_v2_commit(self):
        success = (ROOT / "scripts/dashboard/jobs.py").read_text(encoding="utf-8")
        self.assertIn('"layer": "operational_1.1"', success)
        self.assertIn("EVIDENCE_V2_INCOMPLETE", success)


if __name__ == "__main__":
    unittest.main()
