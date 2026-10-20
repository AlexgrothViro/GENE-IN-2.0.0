import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from resolve_config import resolve_pipeline_config  # noqa: E402

ANALYSIS_PROFILES_CONFIG = str(ROOT / "config" / "analysis_profiles.json")


def _resolved(**overrides):
    kwargs = dict(
        repo_root="/repo",
        sample_name="amostra1",
        incoming={},
        sourced={},
        cli={},
        analysis_profiles_config=ANALYSIS_PROFILES_CONFIG,
    )
    kwargs.update(overrides)
    return resolve_pipeline_config(**kwargs)


class CanonicalPipelineRouteTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = "\n".join((ROOT / "scripts/pipeline" / part).read_text(encoding="utf-8") for part in ("prepare_run.sh", "sample_steps.sh", "run.sh"))
        self.evidence = (ROOT / "scripts/evidence/run.sh").read_text(encoding="utf-8")
        self.makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    def test_canonical_runners_do_not_call_legacy_scripts(self):
        self.assertNotIn("scripts/legacy/", self.pipeline)
        self.assertNotIn("scripts/legacy/", self.evidence)
        self.assertIn("scripts/legacy/ptv/blast.sh", self.makefile)
        self.assertIn("test-blast:", self.makefile)
        self.assertNotIn("scripts/legacy/ptv/blast.sh", self.pipeline)

    def test_pipeline_and_evidence_runners_use_the_single_resolver(self):
        # A configuração deixa de ser resolvida "à mão" em bash: os dois
        # runners chamam o resolvedor único em vez de espalharem lógica de
        # precedência e leitura de política em cada script.
        self.assertIn('resolve_config.py" pipeline', self.pipeline)
        self.assertIn('emit-shell --in "$RESOLVED_CONFIG_JSON"', self.pipeline)
        self.assertNotIn("INCOMING_ASSEMBLER", self.pipeline)
        self.assertNotIn("INCOMING_HOST_FILTER_ENABLED", self.pipeline)

        self.assertIn('resolve_config.py" evidence', self.evidence)
        self.assertIn("emit-shell --in \"$RESOLVED_EVIDENCE_CONFIG_JSON\"", self.evidence)
        self.assertNotIn("cfg() { python3", self.evidence)
        self.assertNotIn('"$EVIDENCE_DIR/config_value.py"', self.evidence)

    def test_experimental_runs_use_the_same_completion_path_as_public(self):
        # Decisão Astra: nenhum desvio pula export/validate/finalize; o
        # caminho técnico de conclusão é o mesmo para experimentos e para
        # o público, com identidade experimental explícita.
        self.assertNotIn('if [[ "$POLICY_CONTEXT" == "experimental" ]]', self.evidence)
        self.assertIn("export_evidence.py", self.evidence)
        self.assertIn("validate_run_artifacts.py", self.evidence)
        self.assertIn("finalize_run.py", self.evidence)
        self.assertIn("EVIDENCE_POLICY_ARGS", self.evidence)
        self.assertIn('--value "activation_policy_context=$POLICY_CONTEXT"', self.evidence)

    def test_host_filter_is_opt_in_and_requires_explicit_selection(self):
        self.assertIn('HOST_FILTER_ENABLED=true exige HOST_NAME explícito.', self.pipeline)
        self.assertIn('HOST_FILTER_ENABLED=true exige HOST_INDEX_PREFIX explícito.', self.pipeline)
        self.assertIn('HOST_FILTER_ENABLED=false; reads seguem sem etapa Bowtie2 de hospedeiro.', self.pipeline)
        self.assertIn('HOST_FILTER_STATUS="disabled_no_host_declared"', self.pipeline)
        self.assertIn("--skip-host-filter", self.pipeline)
        # Comportamento: sem nenhuma entrada explícita, o resolvedor único
        # usado por run.sh mantém o filtro de hospedeiro desativado.
        self.assertEqual(_resolved()["host_filter_enabled"], "false")
        self.assertEqual(
            _resolved(incoming={"HOST_FILTER_ENABLED": "true"})["host_filter_enabled"], "true",
        )

    def test_evidence_v2_is_opt_in_and_not_the_makefile_pipeline_default(self):
        self.assertIn("    --evidence-v2)", self.pipeline)
        self.assertIn('"$SCRIPTS_ROOT/evidence/run.sh"', self.pipeline)
        self.assertNotIn("--evidence-v2", self.makefile)
        # Comportamento: sem --evidence-v2 explícito, o resolvedor mantém a
        # análise Evidence 2.0 desativada por padrão.
        self.assertFalse(_resolved()["evidence"]["v2"])
        self.assertTrue(_resolved(cli={"EVIDENCE_V2": "true"})["evidence"]["v2"])

    def test_evidence_staging_rejects_reuse_without_success(self):
        self.assertIn('STAGING_ROOT="${EVIDENCE_ROOT}/.staging"', self.evidence)
        self.assertIn('run id already has staging or final artifacts', self.evidence)
        self.assertIn("write-failure-evidence", self.evidence)
        self.assertIn("finalize_run.py", self.evidence)
        self.assertIn("SUCCESS.json", (ROOT / "scripts/evidence/finalize_run.py").read_text(encoding="utf-8"))

    def test_valid_blast_database_is_not_rebuilt(self):
        self.assertIn('companions=("${val}".*)', self.pipeline)
        self.assertIn('if ((${#companions[@]} == 0)); then', self.pipeline)
        # A limpeza preventiva de caminhos obsoletos ainda precisa acontecer
        # antes da captura das variáveis "incoming" que o resolvedor usa
        # (BLAST_DB está entre elas).
        self.assertLess(
            self.pipeline.index('unset "$var"'),
            self.pipeline.index("TIER_A_CONFIG_VARS=("),
        )
        self.assertIn("DB DB_QUERY BLAST_DB ASSEMBLER ANALYSIS_PROFILE", self.pipeline)
        self.assertIn("conferindo integridade do manifesto", self.pipeline)
        self.assertIn('validate_blast_database "$BLAST_DB" && [[ -s "$DATABASE_MANIFEST" ]]', self.pipeline)
        # Comportamento: um BLAST_DB explícito no ambiente (equivalente ao
        # antigo INCOMING_BLAST_DB) sempre vence, mesmo quando config.env
        # sourced traz outro valor computado para um DB diferente.
        resolved = _resolved(
            incoming={"BLAST_DB": "/data/explicit_db"},
            sourced={"DB": "ptv", "BLAST_DB": "/data/ptv_db"},
        )
        self.assertEqual(resolved["blast_db"], "/data/explicit_db")

    def test_inline_blast_is_the_canonical_search(self):
        self.assertIn("blastn -task \"$BLAST_TASK\"", self.pipeline)
        self.assertIn("nident gaps", self.pipeline)
        self.assertNotIn("legacy/ptv/blast.sh", self.pipeline)


if __name__ == "__main__":
    unittest.main()
