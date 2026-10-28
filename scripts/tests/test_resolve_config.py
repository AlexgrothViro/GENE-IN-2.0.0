from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from resolve_config import (  # noqa: E402
    ConfigError,
    resolve_evidence_config,
    resolve_pipeline_config,
    resolve_path,
)


def base_pipeline_config(**overrides):
    kwargs = dict(
        repo_root="/repo",
        incoming={},
        sourced={},
        cli={},
        sample_name="amostra1",
        analysis_profiles_config=str(ROOT / "config" / "analysis_profiles.json"),
    )
    kwargs.update(overrides)
    return resolve_pipeline_config(**kwargs)


class ResolvePathTests(unittest.TestCase):
    def test_absolute_path_is_returned_unchanged(self):
        self.assertEqual(resolve_path("/abs/path", "/repo"), "/abs/path")

    def test_relative_path_is_anchored_to_repo_root(self):
        self.assertEqual(resolve_path("data/raw", "/repo"), "/repo/data/raw")

    def test_empty_path_stays_empty(self):
        self.assertEqual(resolve_path("", "/repo"), "")


class PipelinePrecedenceTests(unittest.TestCase):
    """env_first fields: CLI > incoming (pre-source env) > sourced (config file) > default."""

    def test_default_wins_when_nothing_is_provided(self):
        resolved = base_pipeline_config()
        self.assertEqual(resolved["assembler"], "velvet")
        self.assertEqual(resolved["host_name"], "")

    def test_sourced_config_file_value_is_used_when_no_env_or_cli(self):
        resolved = base_pipeline_config(sourced={"ASSEMBLER": "spades"})
        self.assertEqual(resolved["assembler"], "spades")

    def test_incoming_environment_beats_the_config_file(self):
        resolved = base_pipeline_config(
            incoming={"ASSEMBLER": "metaspades"}, sourced={"ASSEMBLER": "spades"},
        )
        self.assertEqual(resolved["assembler"], "metaspades")

    def test_cli_override_beats_incoming_environment(self):
        resolved = base_pipeline_config(
            cli={"ASSEMBLER": "spades"}, incoming={"ASSEMBLER": "metaspades"},
        )
        self.assertEqual(resolved["assembler"], "spades")

    def test_tier_b_field_config_file_beats_a_value_only_present_as_incoming(self):
        # THREADS is never captured before sourcing (config_first): the resolver
        # must ignore any "incoming" layer for it and use the post-source
        # ("sourced") value, exactly like plain bash `source` overwriting a
        # pre-existing environment variable.
        resolved = base_pipeline_config(
            incoming={"THREADS": "16"}, sourced={"THREADS": "8"},
        )
        self.assertEqual(resolved["threads"], 8)

    def test_tier_b_cli_override_still_wins(self):
        resolved = base_pipeline_config(cli={"THREADS": "2"}, sourced={"THREADS": "8"})
        self.assertEqual(resolved["threads"], 2)


class PipelineValidationTests(unittest.TestCase):
    def test_threads_out_of_range_is_rejected(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(sourced={"THREADS": "0"})
        with self.assertRaises(ConfigError):
            base_pipeline_config(sourced={"THREADS": "257"})

    def test_velvet_k_out_of_range_is_rejected(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(sourced={"VELVET_K": "14"})
        with self.assertRaises(ConfigError):
            base_pipeline_config(sourced={"VELVET_K": "128"})

    def test_assembler_enum_is_enforced(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(sourced={"ASSEMBLER": "bwa"})

    def test_builder_is_opt_in_and_the_default_stays_velvet(self):
        self.assertEqual(base_pipeline_config()["assembler"], "velvet")
        resolved = base_pipeline_config(cli={"ASSEMBLER": "builder"})
        self.assertEqual(resolved["assembler"], "builder")
        self.assertEqual(resolved["analysis_strategy"], "single")

    def test_blast_task_enum_is_enforced(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(sourced={"BLAST_TASK": "megablast"})

    def test_host_filter_enabled_accepts_the_documented_aliases(self):
        for value, expected in (
            ("true", "true"), ("1", "true"), ("yes", "true"), ("sim", "true"),
            ("false", "false"), ("0", "false"), ("no", "false"), ("nao", "false"),
        ):
            with self.subTest(value=value):
                resolved = base_pipeline_config(incoming={"HOST_FILTER_ENABLED": value})
                self.assertEqual(resolved["host_filter_enabled"], expected)

    def test_host_filter_enabled_rejects_unknown_values(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(incoming={"HOST_FILTER_ENABLED": "maybe"})


class ConsensusProfileTests(unittest.TestCase):
    def test_consensus_profile_forces_the_assembler(self):
        resolved = base_pipeline_config(cli={"ANALYSIS_PROFILE": "assembly-consensus"})
        self.assertEqual(resolved["assembler"], "consensus")
        self.assertEqual(resolved["analysis_strategy"], "consensus")

    def test_consensus_profile_rejects_an_explicit_assembler_override(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(
                cli={"ANALYSIS_PROFILE": "assembly-consensus", "ASSEMBLER": "spades"},
            )

    def test_unknown_analysis_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            base_pipeline_config(cli={"ANALYSIS_PROFILE": "does-not-exist"})


class BlastDatabasePrecedenceTests(unittest.TestCase):
    def test_default_blast_db_follows_the_db_name(self):
        resolved = base_pipeline_config(incoming={"DB": "fmdv"})
        self.assertEqual(resolved["blast_db"], "/repo/blastdb/fmdv")

    def test_config_file_blast_db_is_honoured_when_db_identity_is_unchanged(self):
        resolved = base_pipeline_config(sourced={"DB": "ptv", "BLAST_DB": "/data/custom_db"})
        self.assertEqual(resolved["blast_db"], "/data/custom_db")

    def test_stale_config_file_blast_db_is_discarded_when_db_changes_via_env(self):
        # The config file's BLAST_DB was computed for the *old* DB; changing
        # DB through the environment must not drag a stale path along.
        resolved = base_pipeline_config(
            incoming={"DB": "fmdv"}, sourced={"DB": "ptv", "BLAST_DB": "/data/ptv_db"},
        )
        self.assertEqual(resolved["blast_db"], "/repo/blastdb/fmdv")

    def test_explicit_incoming_blast_db_always_wins(self):
        resolved = base_pipeline_config(
            incoming={"DB": "fmdv", "BLAST_DB": "/data/explicit_db"},
            sourced={"DB": "ptv", "BLAST_DB": "/data/ptv_db"},
        )
        self.assertEqual(resolved["blast_db"], "/data/explicit_db")

    def test_db_query_switches_db_to_custom_and_discards_stale_blast_db(self):
        resolved = base_pipeline_config(
            incoming={"DB_QUERY": "some query"}, sourced={"DB": "ptv", "BLAST_DB": "/data/ptv_db"},
        )
        self.assertEqual(resolved["db"], "custom")
        self.assertEqual(resolved["db_query"], "some query")
        self.assertEqual(resolved["blast_db"], "/repo/blastdb/custom")


class InputModeTests(unittest.TestCase):
    def test_contigs_input_disables_reads_and_resolves_the_path(self):
        resolved = base_pipeline_config(
            cli={"CONTIGS": "my_contigs.fa"},
            sourced={"SAMPLE_R1": "reads_R1.fastq.gz"},
        )
        self.assertEqual(resolved["input_mode"], "CONTIGS")
        self.assertEqual(resolved["contigs"], "/repo/my_contigs.fa")
        self.assertEqual(resolved["sample_r1"], "")

    def test_reads_default_to_the_sample_name_under_raw_dir(self):
        resolved = base_pipeline_config()
        self.assertEqual(resolved["sample_r1"], "/repo/data/raw/amostra1_R1.fastq.gz")
        self.assertEqual(resolved["sample_r2"], "/repo/data/raw/amostra1_R2.fastq.gz")

    def test_sample_single_alone_is_accepted(self):
        resolved = base_pipeline_config(sourced={"SAMPLE_SINGLE": "single.fastq.gz"})
        self.assertEqual(resolved["sample_single"], "/repo/single.fastq.gz")
        self.assertEqual(resolved["sample_r1"], "")
        self.assertEqual(resolved["sample_r2"], "")

    def test_sample_pair_alone_is_accepted(self):
        resolved = base_pipeline_config(
            sourced={"SAMPLE_R1": "reads_R1.fastq.gz", "SAMPLE_R2": "reads_R2.fastq.gz"},
        )
        self.assertEqual(resolved["sample_r1"], "/repo/reads_R1.fastq.gz")
        self.assertEqual(resolved["sample_r2"], "/repo/reads_R2.fastq.gz")
        self.assertEqual(resolved["sample_single"], "")

    def test_sample_single_together_with_r1_r2_is_rejected(self):
        # GEN-005F1-R1: a guarda de exclusão mútua existia em run.sh:427-429
        # antes do resolvedor único e foi perdida na extração; ambos
        # informados juntos precisa continuar sendo um erro explícito, nunca
        # uma preferência silenciosa por um dos dois lados.
        with self.assertRaises(ConfigError):
            base_pipeline_config(
                sourced={
                    "SAMPLE_SINGLE": "single.fastq.gz",
                    "SAMPLE_R1": "reads_R1.fastq.gz",
                    "SAMPLE_R2": "reads_R2.fastq.gz",
                },
            )

    def test_sample_single_together_with_only_r1_is_rejected(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(
                sourced={"SAMPLE_SINGLE": "single.fastq.gz", "SAMPLE_R1": "reads_R1.fastq.gz"},
            )

    def test_contigs_input_bypasses_the_single_vs_pair_guard(self):
        # CONTIGS clears every read input before the guard would run, so
        # supplying it alongside SAMPLE_SINGLE/SAMPLE_R1/SAMPLE_R2 is not the
        # conflict this guard exists for.
        resolved = base_pipeline_config(
            cli={"CONTIGS": "my_contigs.fa"},
            sourced={"SAMPLE_SINGLE": "single.fastq.gz", "SAMPLE_R1": "reads_R1.fastq.gz"},
        )
        self.assertEqual(resolved["input_mode"], "CONTIGS")
        self.assertEqual(resolved["sample_single"], "")
        self.assertEqual(resolved["sample_r1"], "")


class ReservationTokenTests(unittest.TestCase):
    def test_reservation_token_only_ever_comes_from_the_incoming_environment(self):
        resolved = base_pipeline_config(
            incoming={"EVIDENCE_RESERVATION_TOKEN": "tok-123"},
            sourced={"EVIDENCE_RESERVATION_TOKEN": "tok-from-config-file"},
        )
        self.assertEqual(resolved["evidence"]["reservation_token"], "tok-123")

    def test_reservation_token_is_never_read_from_the_config_file_alone(self):
        resolved = base_pipeline_config(sourced={"EVIDENCE_RESERVATION_TOKEN": "tok-from-config-file"})
        self.assertEqual(resolved["evidence"]["reservation_token"], "")


class EvidenceConfigTests(unittest.TestCase):
    def test_public_policy_is_loaded_once_with_full_identity_and_thresholds(self):
        resolved = resolve_evidence_config(
            activation_policy_path=None,
            profiles_path=None,
            experimental=False,
            role="sample",
            qc_status="unknown",
            host_filter_status="unknown",
        )
        self.assertEqual(resolved["policy_context"], "public")
        self.assertEqual(
            set(resolved["policy_identity"]),
            {"profile_id", "profile_version", "profile_sha256", "activation_record_id", "activation_record_sha256"},
        )
        self.assertIn("locus", resolved["thresholds"])
        self.assertIn("gap_bp", resolved["thresholds"]["locus"])
        self.assertFalse(resolved["shadow_mode"])

    def test_invalid_role_is_rejected(self):
        with self.assertRaises(ConfigError):
            resolve_evidence_config(
                activation_policy_path=None, profiles_path=None, experimental=False,
                role="not-a-role", qc_status="unknown", host_filter_status="unknown",
            )

    def test_invalid_qc_status_is_rejected(self):
        with self.assertRaises(ConfigError):
            resolve_evidence_config(
                activation_policy_path=None, profiles_path=None, experimental=False,
                role="sample", qc_status="not-a-status", host_filter_status="unknown",
            )

    def test_invalid_host_filter_status_is_rejected(self):
        with self.assertRaises(ConfigError):
            resolve_evidence_config(
                activation_policy_path=None, profiles_path=None, experimental=False,
                role="sample", qc_status="unknown", host_filter_status="not-a-status",
            )


class CliRoundTripTests(unittest.TestCase):
    def test_pipeline_cli_writes_a_json_document_readable_by_get_and_emit_shell(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "resolved_config.json"
            subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "resolve_config.py"),
                    "pipeline", "--repo-root", "/repo", "--sample-name", "amostra1",
                    "--analysis-profiles-config", str(ROOT / "config" / "analysis_profiles.json"),
                    "--sourced", "ASSEMBLER=spades", "--out", str(out),
                ],
                check=True, capture_output=True, text=True,
            )
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["assembler"], "spades")

            get = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "resolve_config.py"),
                    "get", "--in", str(out), "--field", "assembler",
                ],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(get.stdout.strip(), "spades")

            emitted = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "resolve_config.py"),
                    "emit-shell", "--in", str(out),
                ],
                check=True, capture_output=True, text=True,
            )
            self.assertIn("ASSEMBLER=spades", emitted.stdout)

    def test_evidence_cli_writes_policy_identity_and_thresholds(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "resolved_config.json"
            subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "resolve_config.py"),
                    "evidence", "--role", "sample", "--qc-status", "unknown",
                    "--host-filter-status", "unknown", "--out", str(out),
                ],
                check=True, capture_output=True, text=True,
            )
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["policy_context"], "public")
            self.assertIn("thresholds", data)


class SearchProfileContractTests(unittest.TestCase):
    """GEN-013: A is the public default; B and C only run when asked for."""

    def test_default_run_selects_only_profile_a(self):
        resolved = base_pipeline_config()
        profile = resolved["search_profile"]
        self.assertEqual(profile["requested"], "")
        self.assertEqual(profile["selected"], "A")
        self.assertEqual(profile["identity"], "search-profile:A")
        self.assertTrue(profile["a_active"])
        self.assertFalse(profile["b_active"])
        self.assertFalse(profile["c_active"])

    def test_default_run_leaves_every_optional_search_flag_off(self):
        resolved = base_pipeline_config()
        self.assertFalse(resolved["short_fragment"]["mode"])
        self.assertFalse(resolved["short_fragment"]["blast"])
        self.assertEqual(resolved["evidence"]["composite_db"], "")
        self.assertFalse(resolved["evidence"]["v2"])
        # O padrão científico da busca A permanece intacto.
        self.assertEqual(resolved["blast_task"], "blastn")
        self.assertEqual(resolved["blast_word_size"], 11)
        self.assertEqual(resolved["blast_evalue"], "1e-5")

    def test_explicit_profile_c_turns_on_extraction_and_short_blast(self):
        resolved = base_pipeline_config(cli={"SEARCH_PROFILES": "C"})
        self.assertTrue(resolved["short_fragment"]["mode"])
        self.assertTrue(resolved["short_fragment"]["blast"])
        self.assertEqual(resolved["search_profile"]["selected"], "A+C")
        self.assertEqual(resolved["search_profile"]["identity"], "search-profile:A+C")
        self.assertEqual(resolved["search_profile"]["requested"], "C")
        # C usa o mesmo banco direcionado de A e não mexe no BLAST de contigs.
        self.assertEqual(resolved["blast_task"], "blastn")
        self.assertEqual(resolved["blast_db"], "/repo/blastdb/custom")

    def test_explicit_profile_b_requires_the_curated_composite_db(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(cli={"SEARCH_PROFILES": "B"})

    def test_explicit_profile_b_uses_the_composite_panel(self):
        resolved = base_pipeline_config(
            cli={"SEARCH_PROFILES": "B"},
            incoming={"EVIDENCE_COMPOSITE_DB": "/panel/composite"},
        )
        self.assertEqual(resolved["search_profile"]["selected"], "A+B")
        self.assertEqual(resolved["evidence"]["composite_db"], "/panel/composite")
        self.assertFalse(resolved["short_fragment"]["mode"])
        self.assertFalse(resolved["short_fragment"]["blast"])

    def test_named_combination_keeps_every_selected_profile_in_the_identity(self):
        resolved = base_pipeline_config(
            cli={"SEARCH_PROFILES": "C,B"},
            incoming={"EVIDENCE_COMPOSITE_DB": "/panel/composite"},
        )
        profile = resolved["search_profile"]
        self.assertEqual(profile["requested"], "B,C")
        self.assertEqual(profile["selected"], "A+B+C")
        self.assertEqual(profile["identity"], "search-profile:A+B+C")
        self.assertTrue(profile["b_active"] and profile["c_active"])

    def test_profile_selected_through_the_pre_existing_flags_is_still_recorded(self):
        resolved = base_pipeline_config(incoming={"SHORT_FRAGMENT_BLAST": "true"})
        self.assertEqual(resolved["search_profile"]["requested"], "")
        self.assertEqual(resolved["search_profile"]["selected"], "A+C")

    def test_unknown_profile_label_is_rejected(self):
        with self.assertRaises(ConfigError):
            base_pipeline_config(cli={"SEARCH_PROFILES": "D"})

    def test_emit_shell_exposes_the_profile_identity_to_the_pipeline(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "resolved_config.json"
            subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "resolve_config.py"),
                    "pipeline", "--repo-root", tmp, "--sample-name", "amostra1",
                    "--analysis-profiles-config", str(ROOT / "config" / "analysis_profiles.json"),
                    "--cli", "SEARCH_PROFILES=C", "--out", str(out),
                ],
                check=True, capture_output=True, text=True,
            )
            emitted = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "resolve_config.py"),
                    "emit-shell", "--in", str(out),
                ],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertIn("SEARCH_PROFILE_SELECTED=A+C", emitted)
            self.assertIn("SEARCH_PROFILE_C_ACTIVE=true", emitted)
            self.assertIn("SEARCH_PROFILE_B_ACTIVE=false", emitted)
            self.assertIn("SHORT_FRAGMENT_MODE=true", emitted)
            self.assertIn("SHORT_FRAGMENT_BLAST=true", emitted)


if __name__ == "__main__":
    unittest.main()
