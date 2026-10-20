"""Distribution 2.0.1 keeps the frozen Evidence contract version."""
import json
import unittest
from pathlib import Path

import tomllib


ROOT = Path(__file__).resolve().parents[2]


class SoftwareVersionTests(unittest.TestCase):
    def test_distribution_is_2_0_1_and_the_evidence_contract_stays_locked(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8")
        self.assertEqual(version, "2.0.0-alpha.2\n")
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        release = json.loads((ROOT / "RELEASE.json").read_text(encoding="utf-8"))
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertEqual(project["project"]["version"], "2.0.1")
        self.assertEqual(release["software_version"], "2.0.1")
        self.assertEqual(release["evidence_contract"], "2.0.0-alpha.2")
        self.assertIn("version: 2.0.1\n", citation)


if __name__ == "__main__":
    unittest.main()
