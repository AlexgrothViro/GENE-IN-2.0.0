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


if __name__ == "__main__":
    unittest.main()
