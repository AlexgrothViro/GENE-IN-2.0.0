import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from activation_policy import (
    conclusion_for,
    load_experimental_activation_policy,
    load_public_activation_policy,
    policy_identity,
)
from analysis_profiles import load_profiles, resolve_profile
from assembly_consensus import combine, locus_concordance
from evidence_profile import canonical_sha256, load_profile, validate_gate_results




class AnalysisProfileTests(unittest.TestCase):
    def test_profiles_are_typed_and_consensus_requires_two_assemblers(self):
        config = load_profiles(ROOT / "config/analysis_profiles.json")
        profile_id, profile = resolve_profile(config, "assembly-consensus")
        self.assertEqual(profile_id, "assembly-consensus")
        self.assertEqual(profile["assembly"]["strategy"], "consensus")
        self.assertEqual(profile["assembly"]["minimum_successful_assemblers"], 2)
        self.assertEqual(profile["evidence_ceiling"], "UNRESTRICTED")
        self.assertTrue(all(plugin["evidence_authority"] == "ANALYSIS" for plugin in config["plugins"]))



class AssemblyConsensusTests(unittest.TestCase):
    def test_exact_and_locus_concordance_are_observational(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            velvet, spades, metaspades = root / "velvet.fa", root / "spades.fa", root / "metaspades.fa"
            shared = "ACGT" * 75
            velvet.write_text(f">v1\n{shared}\n>v2\n{'A' * 240}\n", encoding="utf-8")
            spades.write_text(f">s1\n{shared}\n>s2\n{'C' * 250}\n", encoding="utf-8")
            metaspades.write_text(f">m1\n{shared}\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest = combine(
                {"velvet": velvet, "spades": spades, "metaspades": metaspades},
                {"velvet": "SUCCESS", "spades": "SUCCESS", "metaspades": "SUCCESS"},
                root / "combined.fa", manifest_path, 2, "assembly-consensus",
            )
            self.assertTrue(manifest["consensus_requirement_met"])
            shared_query = next(item["query_id"] for item in manifest["sequences"] if item["support_count"] == 3)
            loci = root / "loci.tsv"
            loci.write_text("sseqid\tcategory\tlocus_id\tquery_ids\n" f"virus\tTARGET_VIRUS\tL1\t{shared_query}\n", encoding="utf-8")
            result = locus_concordance(loci, manifest_path, root / "concordance.tsv", root / "concordance.json")
            self.assertEqual(result["multi_assembler_locus_count"], 1)
            self.assertEqual(result["evidence_authority"], "ANALYSIS")


class ProfileIntegrityTests(unittest.TestCase):
    """Equivalent coverage for the three pre-D1 checks that are not obsolete:
    hash mismatch, invalid outcome and closed schema still fail closed under
    the current open-analysis contract, even with gates=[] and no shadow mode.
    """

    def test_activation_rejects_profile_hash_mismatch(self):
        activation_path = ROOT / "config" / "evidence_activation.json"
        profiles_path = ROOT / "config" / "evidence_profiles.json"
        record = json.loads(activation_path.read_text(encoding="utf-8"))
        record["target_profile"]["expected_profile_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "evidence_activation.json"
            tampered.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_experimental_activation_policy(tampered, profiles_path=profiles_path)
            self.assertIn("expected_profile_sha256", str(ctx.exception))

    def test_conclusion_for_rejects_unsupported_outcome(self):
        policy = load_public_activation_policy(
            ROOT / "config" / "evidence_activation.json",
            profiles_path=ROOT / "config" / "evidence_profiles.json",
        )
        for legacy_outcome in ("SUPPORT_NOT_PASSED", "BLOCKED", "shadow_only"):
            with self.assertRaises(ValueError):
                conclusion_for(policy, legacy_outcome)

    def test_profile_schema_rejects_unknown_field_and_empty_gate_catalog(self):
        profiles_path = ROOT / "config" / "evidence_profiles.json"
        catalog = json.loads(profiles_path.read_text(encoding="utf-8"))
        catalog["profiles"]["open-analysis"]["unexpected_field"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "evidence_profiles.json"
            tampered.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_profile("open-analysis", tampered)
            self.assertIn("unknown fields", str(ctx.exception))
        profile = load_profile("open-analysis", profiles_path)
        self.assertEqual(profile["gates"], [])
        with self.assertRaises(ValueError):
            validate_gate_results(profile, [{"gate_id": "e1_canonical", "status": "PASS", "reason": "legacy"}])

    def test_policy_identity_rejects_malformed_digest(self):
        policy = load_public_activation_policy(
            ROOT / "config" / "evidence_activation.json",
            profiles_path=ROOT / "config" / "evidence_profiles.json",
        )
        broken = dict(policy_identity(policy))
        broken["profile_sha256"] = "not-a-hex-digest"
        with self.assertRaises(ValueError):
            from activation_policy import validate_policy_identity
            validate_policy_identity(broken)


if __name__ == "__main__":
    unittest.main()
