"""Distribution 2.0.2 keeps the frozen Evidence contract version."""
import json
import unittest
from pathlib import Path

import tomllib


ROOT = Path(__file__).resolve().parents[2]


class SoftwareVersionTests(unittest.TestCase):
    def test_distribution_is_2_0_2_and_the_evidence_contract_stays_locked(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8")
        self.assertEqual(version, "2.0.0-alpha.2\n")
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        release = json.loads((ROOT / "RELEASE.json").read_text(encoding="utf-8"))
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertEqual(project["project"]["version"], "2.0.2")
        self.assertEqual(release["software_version"], "2.0.2")
        self.assertEqual(release["evidence_contract"], "2.0.0-alpha.2")
        self.assertEqual(release["closure_commit"], "42a2c135666337b025b9cd1cdde5b8ae208831f6")
        self.assertNotIn("53af26ba", json.dumps(release))
        self.assertNotIn("53af26ba", (ROOT / "docs/citacao.md").read_text(encoding="utf-8"))
        self.assertNotIn("fb2f57a", json.dumps(release))
        self.assertNotIn("base_commit", release)
        self.assertEqual(release["integration_base_commit"], "96f0932884ae2e8ebe6b580b0c33fbaffc048266")
        citation_guide = (ROOT / "docs/citacao.md").read_text(encoding="utf-8")
        self.assertNotIn("fb2f57a", citation_guide)
        self.assertIn("não está neste repositório público", citation_guide)
        self.assertIn("não está neste repositório público", release["candidate_version_note"])
        self.assertIn("version: 2.0.2\n", citation)


if __name__ == "__main__":
    unittest.main()
