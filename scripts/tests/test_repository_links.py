"""Public links point at this repository, not the previous name."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
URL = "https://github.com/AlexgrothViro/GENE-IN-2.0.0"
OLD = "https://github.com/AlexgrothViro/gene-in-estabilizado"


class RepositoryLinkTests(unittest.TestCase):
    def test_readme_and_metadata_use_this_repository(self):
        for relative in ("README.md", "README.en.md", "RELEASE.json", "CITATION.cff", "pyproject.toml", "docs/citacao.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(URL, text, relative)
            self.assertNotIn(OLD, text, relative)

    def test_historical_repository_names_are_not_published_as_links(self):
        names = (
            "GENE_IN-ALPHA", "Gene-in-Alpha-pre-release", "Gene-in-Alpha-2",
            "Gene-In-Limitado", "Gene-in-private", "Gene-In", "Gene-In_1.1", "Gene-In_1.0",
        )
        history = (ROOT / "docs/repositorios-e-historico.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8") + (ROOT / "README.en.md").read_text(encoding="utf-8")
        for name in names:
            self.assertIn(f"`{name}`", history)
            self.assertNotIn(f"https://github.com/AlexgrothViro/{name}", history)
            self.assertNotIn(f"https://github.com/AlexgrothViro/{name}", readme)
        warning = (ROOT / "scripts/ops/check_env.sh").read_text(encoding="utf-8")
        self.assertIn("install_linux.sh", warning)
        self.assertIn("bundle/install_wsl.sh não usam rsync", warning)
        self.assertNotIn('[[ "$cmd" == "rsync" && -n "${GENEIN_WORK_ROOT:-}" ]]', warning)


if __name__ == "__main__":
    unittest.main()
