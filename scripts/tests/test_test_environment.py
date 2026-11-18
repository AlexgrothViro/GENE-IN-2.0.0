"""The test entry point must not install into a system Python."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "posix", "PULOU: requer Bash/POSIX")
class TestEnvironmentTests(unittest.TestCase):
    def test_make_test_gives_venv_message_without_calling_system_pip(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            binary = work / "python3"
            calls = work / "calls.txt"
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CONTROLLED_CALLS"\nexit 1\n')
            binary.chmod(0o755)
            env = {**os.environ, "PATH": str(work) + ":/usr/bin:/bin", "CONTROLLED_CALLS": str(calls), "GENEIN_CONFIG_FILE": str(work / "absent.env")}
            result = subprocess.run(["make", "--no-print-directory", "test"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn("make test precisa de um venv", result.stdout + result.stderr)
            self.assertNotIn("-m pip", calls.read_text())


if __name__ == "__main__":
    unittest.main()
