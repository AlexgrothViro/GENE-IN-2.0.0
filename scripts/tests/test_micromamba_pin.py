"""The installer pins micromamba instead of downloading an unversioned latest build."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PIN_VERSION = "2.9.0"
PIN_SHA256 = "8761c382127e6363bd9e0a2451aa3ef90d071a79133f736e2f759a3bf13040dd"


class MicromambaPinTests(unittest.TestCase):
    def test_user_installers_pin_the_tarball_version_and_hash(self):
        for relative in ("bundle/install_wsl.sh", "install_linux.sh"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertIn(PIN_VERSION, text)
                self.assertIn(PIN_SHA256, text)
                self.assertIn("sha256sum", text)
                self.assertNotIn("linux-64/latest", text)
                self.assertIn("bin/micromamba", text)


if __name__ == "__main__":
    unittest.main()
