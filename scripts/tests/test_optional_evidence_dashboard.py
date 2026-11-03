"""Optional-input integration, using artificial files and a controlled index inspector."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/pipeline")]
from dashboard.evidence_options import optional_evidence_inputs
from dashboard.jobs import build_command
from resolve_config import resolve_pipeline_config


class OptionalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="optional files ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prefix = self.root / "fixture-bank"
        component = Path(str(self.prefix) + ".nsq")
        component.write_bytes(b"controlled metadata only")
        self.manifest = Path(str(self.prefix) + ".db-manifest.json")
        self.manifest.write_text(json.dumps({"schema_version": "1.0", "produced_files": {component.name: {"size": component.stat().st_size, "sha256": hashlib.sha256(component.read_bytes()).hexdigest()}}}))
        self.labels = self.root / "labels.tsv"
        self.labels.write_text("sseqid\tcategory\nfixture-target\tTARGET_VIRUS\nfixture-other\tHOST\n")
        self.reference = self.root / "reference.fa"
        self.reference.write_text(">artificial\nACGT\n")
        self.index = self.root / "fixture-index"
        for suffix in ("1", "2", "3", "4", "rev.1", "rev.2"):
            Path(str(self.index) + f".{suffix}.bt2").write_bytes(b"controlled index placeholder")
        Path(str(self.index) + ".fixture.fa").write_text(self.reference.read_text())
        binary = self.root / "bin/bowtie2-inspect"
        binary.parent.mkdir()
        binary.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nimport sys\nprefix=sys.argv[1]\nassert all(Path(prefix+"."+part+".bt2").is_file() for part in ("1","2","3","4","rev.1","rev.2"))\nprint(Path(prefix+".fixture.fa").read_text(),end="")\n')
        binary.chmod(0o755)
        database_inspector = binary.parent / "blastdbcmd"
        database_inspector.write_text('#!/usr/bin/env python3\nprint("fixture-target\\nfixture-other")\n')
        database_inspector.chmod(0o755)
        self.config = self.root / "fixture.env"
        self.config.write_text("")
        patched = patch.dict(os.environ, {"PATH": str(binary.parent) + os.pathsep + os.environ.get("PATH", ""), "GENEIN_CONFIG_FILE": str(self.config)})
        patched.start()
        self.addCleanup(patched.stop)
        self.params = {"competition_enabled": True, "competition_db": str(self.prefix), "competition_labels": str(self.labels), "remapping_enabled": True, "remapping_reference": str(self.reference), "remapping_index": str(self.index), "library_mode": "unknown"}

    def test_each_combination_reaches_the_canonical_resolver(self):
        for competition, remapping in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(competition=competition, remapping=remapping):
                params = {**self.params, "competition_enabled": competition, "remapping_enabled": remapping}
                command, env = build_command("evidence_pipeline", {**params, "sample": "fixture", "db": "fixture-bank"})
                self.assertIn("--evidence-v2", command)
                resolved = resolve_pipeline_config(repo_root=str(ROOT), sample_name="fixture", incoming=env, sourced={}, cli={})
                self.assertEqual(bool(resolved["evidence"]["composite_db"]), competition)
                self.assertEqual(bool(resolved["evidence"]["subject_labels"]), competition)
                self.assertEqual(bool(resolved["evidence"]["panel_fasta"]), remapping)
                self.assertEqual(bool(resolved["evidence"]["panel_index"]), remapping)
                self.assertEqual(resolved["search_profile"]["b_active"], competition)

    def test_off_overrides_previous_config_and_does_not_read_inactive_paths(self):
        env, _ = optional_evidence_inputs({"competition_enabled": False, "remapping_enabled": False, "competition_db": "/missing"})
        old = {"EVIDENCE_COMPOSITE_DB": "old", "EVIDENCE_SUBJECT_LABELS": "old", "EVIDENCE_PANEL_FASTA": "old", "EVIDENCE_PANEL_INDEX": "old"}
        resolved = resolve_pipeline_config(repo_root=str(ROOT), sample_name="fixture", incoming=env, sourced=old, cli={})
        self.assertEqual(resolved["search_profile"]["selected"], "A")
        for name in ("composite_db", "subject_labels", "panel_fasta", "panel_index"):
            self.assertEqual(resolved["evidence"][name], "")

    def test_old_callers_without_option_switches_keep_their_existing_config(self):
        env, _ = optional_evidence_inputs({})
        self.assertEqual(env, {})
        resolved = resolve_pipeline_config(repo_root=str(ROOT), sample_name="fixture", incoming=env, sourced={"EVIDENCE_COMPOSITE_DB": "existing", "EVIDENCE_PANEL_FASTA": "existing"}, cli={})
        self.assertEqual(resolved["evidence"]["composite_db"], "existing")
        self.assertEqual(resolved["evidence"]["panel_fasta"], "existing")

    def test_paths_with_spaces_and_hash_receipts_are_preserved(self):
        env, receipt = optional_evidence_inputs(self.params)
        self.assertEqual(env["EVIDENCE_PANEL_FASTA"], str(self.reference))
        self.assertEqual(receipt["remapping"]["reference_sha256"], hashlib.sha256(self.reference.read_bytes()).hexdigest())
        self.assertEqual(receipt["competition"]["label_count"], 2)

    def test_missing_and_tampered_database_are_rejected(self):
        self.manifest.unlink()
        with self.assertRaises(ValueError):
            optional_evidence_inputs(self.params)

    def test_tampered_component_is_rejected(self):
        Path(str(self.prefix) + ".nsq").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "alterado|incompleto"):
            optional_evidence_inputs(self.params)

    def test_missing_or_invalid_labels_are_rejected(self):
        for text in ("bad\theader\n", "sseqid\tcategory\nx\tUNKNOWN\n", "sseqid\tcategory\nx\tTARGET_VIRUS\n", "sseqid\tcategory\nx\tTARGET_VIRUS\nx\tHOST\n"):
            with self.subTest(text=text):
                self.labels.write_text(text)
                with self.assertRaises(ValueError):
                    optional_evidence_inputs(self.params)

    def test_mapping_identity_is_rechecked_after_a_previous_validation(self):
        optional_evidence_inputs(self.params)
        self.reference.write_text(">artificial\nAAAA\n")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            optional_evidence_inputs(self.params)

    def test_incomplete_mapping_index_fails(self):
        Path(str(self.index) + ".4.bt2").unlink()
        with self.assertRaises(ValueError):
            optional_evidence_inputs(self.params)

    def test_bad_switch_type_and_library_mode_are_rejected(self):
        for option in ("competition_enabled", "remapping_enabled"):
            with self.subTest(option=option), self.assertRaises(ValueError):
                optional_evidence_inputs({option: "false"})
        with self.assertRaisesRegex(ValueError, "biblioteca"):
            optional_evidence_inputs({**self.params, "library_mode": "invented"})

    def test_real_shell_boundary_preserves_the_explicit_choices_before_analysis(self):
        shell_root = self.root / "shell source"
        pipeline = shell_root / "scripts/pipeline"
        pipeline.mkdir(parents=True)
        (shell_root / "scripts/lib").symlink_to(ROOT / "scripts/lib", target_is_directory=True)
        for name in ("run_sample.sh", "prepare_run.sh"):
            shutil.copy2(ROOT / "scripts/pipeline" / name, pipeline / name)
        for name in ("resolve_config.py", "analysis_profiles.py"):
            (pipeline / name).symlink_to(ROOT / "scripts/pipeline" / name)
        steps = (ROOT / "scripts/pipeline/sample_steps.sh").read_text()
        (pipeline / "sample_steps.sh").write_text(steps[:steps.index("# A identidade de DB")] + '\ncat "$RESOLVED_CONFIG_JSON"\n')
        config = shell_root / "fixture.env"
        config.write_text('THREADS=4\nASSEMBLER=velvet\nEVIDENCE_COMPOSITE_DB=previous\nEVIDENCE_SUBJECT_LABELS=previous\nEVIDENCE_PANEL_FASTA=previous\nEVIDENCE_PANEL_INDEX=previous\n')
        work = shell_root / "work"
        work.mkdir()
        for selected in (False, True):
            with self.subTest(selected=selected):
                optional_env, _ = optional_evidence_inputs({**self.params, "competition_enabled": selected, "remapping_enabled": selected})
                env = {**os.environ, **optional_env, "GENEIN_CONFIG_FILE": str(config), "GENEIN_WORK_ROOT": str(work), "ANALYSIS_PROFILES_CONFIG": str(ROOT / "config/analysis_profiles.json")}
                result = subprocess.run(["bash", str(pipeline / "run_sample.sh"), "--sample", "fixture", "--evidence-v2"], env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                resolved = json.loads(result.stdout)
                self.assertEqual(bool(resolved["evidence"]["composite_db"]), selected)
                self.assertEqual(bool(resolved["evidence"]["panel_index"]), selected)
                self.assertEqual(resolved["evidence"]["v2"], True)


if __name__ == "__main__":
    unittest.main()
