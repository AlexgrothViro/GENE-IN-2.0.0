"""Configuration conflict only; no search or analysis is launched."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/pipeline"))
from resolve_config import ConfigError, resolve_pipeline_config


class OptionalProfileConflictTests(unittest.TestCase):
    def resolve(self, switch, layer):
        layers = {"incoming": {}, "sourced": {}, "cli": {}}
        layers[layer] = {"SEARCH_PROFILES": "B", "EVIDENCE_COMPETITION_ENABLED": switch,
                         "EVIDENCE_COMPOSITE_DB": "/fixture/bank", "EVIDENCE_SUBJECT_LABELS": "/fixture/labels.tsv"}
        return resolve_pipeline_config(repo_root=str(ROOT), sample_name="fixture", **layers)

    def test_requested_b_with_competition_false_is_rejected_in_each_layer(self):
        for layer in ("incoming", "sourced", "cli"):
            with self.subTest(layer=layer), self.assertRaisesRegex(ConfigError, "perfil B pedido, mas a competição está desligada"):
                self.resolve("false", layer)

    def test_requested_b_with_competition_true_preserves_request_and_provenance(self):
        for layer in ("incoming", "sourced", "cli"):
            with self.subTest(layer=layer):
                resolved = self.resolve("true", layer)
                self.assertEqual(resolved["search_profile"]["requested"], "B")
                self.assertEqual(resolved["search_profile"]["selected"], "A+B")

    def test_requested_b_with_empty_switch_preserves_legacy_inheritance(self):
        for layer in ("incoming", "sourced", "cli"):
            with self.subTest(layer=layer):
                resolved = self.resolve("", layer)
                self.assertEqual(resolved["search_profile"]["requested"], "B")
                self.assertTrue(resolved["search_profile"]["b_active"])


if __name__ == "__main__":
    unittest.main()
