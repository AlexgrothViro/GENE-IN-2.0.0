import unittest
from pathlib import Path
from unittest import mock

import scripts.ux_dashboard as dashboard


REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = REPO_ROOT / "dashboard" / "index.html"
OPERATIONAL_JS = REPO_ROOT / "dashboard" / "js" / "operational.js"
ADVANCED_JS = REPO_ROOT / "dashboard" / "js" / "advanced.js"


class DashboardGuidedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        cls.operational = OPERATIONAL_JS.read_text(encoding="utf-8")
        cls.advanced = ADVANCED_JS.read_text(encoding="utf-8")

    def test_semantic_shell_and_context_are_present(self):
        for element_id in (
            "primary-navigation", "app-main", "route-view", "notifications", "modal-root",
            "context-environment", "context-database", "context-sample", "context-job",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        for element in ("<header", "<nav", "<main"):
            self.assertIn(element, self.html)

    def test_operational_navigation_precedes_separate_advanced_entry(self):
        labels = ["Início", "Nova análise", "Acompanhar", "Resultados", "Histórico"]
        positions = [self.html.index(f">{label}</a>") for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertGreater(self.html.index(">Área avançada</a>"), positions[-1])
        self.assertNotIn("P&amp;D", self.html)
        self.assertIn("P&D", self.advanced)
        self.assertIn('advanced-entry advanced-entry--mobile', self.html)
        self.assertIn('advanced-entry advanced-entry--desktop', self.html)

    def test_configuration_actions_remain_consumed_by_the_interface(self):
        for endpoint in (
            "/api/config/env", "/api/host-index/validate",
            "/api/config/environment/rebuild",
        ):
            self.assertIn(endpoint, self.advanced)
        for label in ("Salvar configuração", "Validar índice", "Reconstruir ambiente"):
            self.assertIn(label, self.advanced)

    def test_history_results_and_tracking_keep_operational_actions(self):
        for value in (
            "/api/history/rerun", "/api/history/file", "#/results?run=",
            "#/track?job=", "genein.activeJob.v1",
        ):
            sources = self.operational + (REPO_ROOT / "dashboard" / "js" / "state.js").read_text(encoding="utf-8")
            self.assertIn(value, sources)

    def test_sample_import_remains_on_the_operational_flow(self):
        for value in (
            "/api/import-upload", 'action: "import_sample"', "Importar por caminho",
            "zipfile", "Gerar amostra DEMO", "Caminho local (avançado)",
        ):
            self.assertIn(value, self.operational)
        self.assertIn("sampleImportCard", self.advanced)

    def test_wizard_uses_six_stage_reference_flow(self):
        self.assertIn('const WIZARD_STEPS = ["Ambiente", "Banco", "Amostra", "Configuração", "Revisão", "Execução"]', self.operational)
        self.assertIn('action: "evidence_pipeline"', self.operational)
        self.assertNotRegex(self.operational, r'action: "pipeline"')
        self.assertIn('wizard.assembler === "consensus" ? "assembly-consensus" : "default"', self.operational)
        self.assertIn("Nenhuma porcentagem ou previsão é inventada", self.operational)

    def test_execution_gate_has_reason_and_correction_path(self):
        for reason in ("ambiente pendente", "banco não selecionado", "amostra não selecionada"):
            self.assertIn(reason, self.operational)
        self.assertIn("Não é possível executar", self.operational)
        self.assertIn("Corrija:", self.operational)

    def test_preflight_reports_assembler_capability(self):
        with mock.patch("scripts.ux_dashboard.shutil.which", return_value=None):
            result = dashboard.get_preflight_status()
        self.assertFalse(result["ok"])
        self.assertFalse(result["assembler_available"])
        self.assertIn("nenhum montador", result["summary"])

    def test_runtime_environment_preprends_bundled_tool_directory(self):
        env_bin = REPO_ROOT / "tmp" / "gene-in-env" / "bin"
        with mock.patch.object(Path, "is_dir", return_value=True):
            env = dashboard.runtime_environment({"PATH": "/usr/bin", "GENEIN_ENV_BIN": str(env_bin)})
        self.assertTrue(env["PATH"].startswith(str(env_bin)))
        self.assertEqual(env["GENEIN_ENV_BIN"], str(env_bin))

    def test_environment_status_exposes_environment_file_contract(self):
        result = dashboard.get_environment_status()
        self.assertTrue(result["has_environment_yml"])
        self.assertTrue(result["environment_yml_path"].endswith("environment.yml"))
        self.assertTrue(result["environment_yml_mtime"])

    def test_module_allowlist_is_explicit_and_has_no_traversal(self):
        for module in ("main.js", "operational.js", "advanced.js", "analytics.js", "charts.js", "router.js"):
            self.assertIn(module, dashboard.JAVASCRIPT_MODULES)
        self.assertTrue(all("/" not in module and ".." not in module for module in dashboard.JAVASCRIPT_MODULES))

    def test_observable_plot_is_pinned_and_local(self):
        self.assertIn("/vendor/observable-plot-0.6.17.min.js", self.html)
        self.assertNotIn("https://", self.html)
        self.assertTrue((REPO_ROOT / "dashboard/vendor/observable-plot-0.6.17.min.js").is_file())


if __name__ == "__main__":
    unittest.main()
