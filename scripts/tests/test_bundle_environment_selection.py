"""Explicit environment selection must never fall back to a different install."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "posix", "Linux/WSL environment selection")
class BundleSelectionTests(unittest.TestCase):
    def test_missing_explicit_prefix_fails_before_tool_detection(self):
        for key in ("GENEIN_ENV_DIR", "GENEIN_BUNDLE_DIR"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                env = dict(os.environ)
                env.pop("GENEIN_ENV_DIR", None)
                env.pop("GENEIN_BUNDLE_DIR", None)
                env[key] = str(Path(tmp) / "missing")
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts/ops/check_env.sh")],
                    env=env, cwd=tmp, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("solicitado ausente", result.stderr)
                self.assertFalse((Path(tmp) / "logs").exists())


if __name__ == "__main__":
    unittest.main()
