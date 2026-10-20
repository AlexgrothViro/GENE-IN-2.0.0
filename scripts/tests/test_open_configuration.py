from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from activation_policy import load_public_activation_policy, policy_identity
from classify_sample import classify
from validation.experimental_policy import load_experimental_policy, materialize_experimental_policy
from validation.tracks import TRACKS


class OpenConfigurationTests(unittest.TestCase):
    def test_default_profile_has_no_scientific_gate(self):
        policy = load_public_activation_policy()
        self.assertFalse(policy["shadow_mode"])
        self.assertEqual(policy["evidence_ceiling"], "UNRESTRICTED")
        self.assertFalse(policy["diagnostic_language_allowed"])
        self.assertEqual(policy["gates"], [])

    def test_policy_identity_keeps_only_integrity_fields(self):
        self.assertEqual(
            set(policy_identity(load_public_activation_policy())),
            {
                "profile_id",
                "profile_version",
                "profile_sha256",
                "activation_record_id",
                "activation_record_sha256",
            },
        )

    def test_classification_has_no_promotion_gate(self):
        result = classify("sample", [], [], [], [], "UNCONTROLLED", "unknown")
        self.assertEqual(result["promotion_gates"], [])
        self.assertEqual(result["evidence_level"], "NO_SIGNAL")
        self.assertEqual(result["reported_conclusion"], "NO_EVIDENCE_RECOVERED")

    def test_validation_tracks_have_no_tier_metadata(self):
        self.assertNotIn("authorized-pilot", TRACKS)
        self.assertTrue(all(not hasattr(track, "tier") for track in TRACKS.values()))

    def test_parameter_sweep_policy_needs_no_ticket(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            paths = materialize_experimental_policy(
                parameters={}, parameter_set_id="test", out_dir=Path(temporary)
            )
            policy = load_experimental_policy(paths)
            self.assertEqual(policy["scientific_role"], "GENERAL")
            self.assertFalse(policy["shadow_mode"])


if __name__ == "__main__":
    unittest.main()
