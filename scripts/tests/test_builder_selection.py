"""Builder selection and isolated optional environment; no sequence analysis."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.dashboard.jobs import assembly_command_args
from scripts.dashboard.config import validate_config_updates

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("builder_selection_adapter", ROOT / "scripts/pipeline/assemblers/builder_adapter.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class BuilderSelectionTests(unittest.TestCase):
    def test_dashboard_uses_default_profile_and_explicit_builder(self):
        args = assembly_command_args({"assembler": "builder"})
        self.assertIn("builder", args)
        self.assertIn("default", args)
        validate_config_updates({"ASSEMBLER": "builder"})

    def test_consensus_rejects_override(self):
        with self.assertRaises(ValueError):
            assembly_command_args({"assembler": "builder", "analysis_profile": "assembly-consensus"})

    def test_isolated_environment_and_explicit_override(self):
        with TemporaryDirectory() as tmp:
            binary = Path(tmp) / "builder-env/bin/genein-builder"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o755)
            with patch.dict(os.environ, {"GENEIN_BUNDLE_DIR": tmp, "GENEIN_BUILDER_BIN": ""}):
                self.assertEqual(adapter.locate_builder(), [str(binary)])
            other = Path(tmp) / "explicit"
            other.write_text("#!/bin/sh\nexit 0\n")
            other.chmod(0o755)
            with patch.dict(os.environ, {"GENEIN_BUNDLE_DIR": tmp, "GENEIN_BUILDER_BIN": str(other)}):
                self.assertEqual(adapter.locate_builder(), [str(other)])

    def test_check_rejects_old_version_without_execution(self):
        with patch.object(adapter, "locate_builder", return_value=["mock"]), \
             patch.object(adapter, "query_builder_version", return_value="0.2.1"), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(adapter.main(["check"]), 2)
        self.assertIn("0.4.0", error.getvalue())


if __name__ == "__main__":
    unittest.main()
