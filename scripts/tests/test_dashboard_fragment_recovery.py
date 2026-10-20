import unittest

import scripts.ux_dashboard
from dashboard.jobs import build_command


class FragmentRecoveryCommandTests(unittest.TestCase):
    def test_multi_uses_profile_without_individual_override(self):
        for action in ("pipeline", "evidence_pipeline"):
            with self.subTest(action=action):
                command, environment = build_command(action, {"sample": "short_input", "db": "ptv",
                    "assembler": "consensus", "analysis_profile": "assembly-consensus", "kmer": 31})
                self.assertNotIn("--assembler", command)
                self.assertEqual(command[command.index("--analysis-profile") + 1], "assembly-consensus")
                self.assertEqual(command[command.index("--kmer") + 1], "31")
                self.assertEqual(environment["DB"], "ptv")

    def test_single_assembler_remains_available(self):
        command, _ = build_command("evidence_pipeline", {"sample": "sample", "db": "ptv", "assembler": "velvet"})
        self.assertEqual(command[command.index("--assembler") + 1], "velvet")
        self.assertEqual(command[command.index("--analysis-profile") + 1], "default")

    def test_contradictory_selection_is_rejected(self):
        for assembler, profile in (("consensus", "default"), ("spades", "assembly-consensus"), ("consensus", "missing")):
            with self.subTest(assembler=assembler, profile=profile), self.assertRaises(ValueError):
                build_command("evidence_pipeline", {"sample": "sample", "db": "ptv",
                    "assembler": assembler, "analysis_profile": profile})

    def test_library_adapters_are_explicit_and_not_shell_commands(self):
        _, environment = build_command("evidence_pipeline", {"sample": "sample", "db": "ptv", "qc_adapter_r1": "agatcgga"})
        self.assertEqual(environment["QC_ADAPTER_R1"], "AGATCGGA")
        with self.assertRaises(ValueError):
            build_command("evidence_pipeline", {"sample": "sample", "db": "ptv", "qc_adapter_r1": "ACGT;exit"})


if __name__ == "__main__":
    unittest.main()
