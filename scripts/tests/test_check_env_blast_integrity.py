"""check_env must not claim success after a corrupt BLAST DB or invalid manifest."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def _stub(directory: Path, name: str, body: str = "#!/bin/sh\nexit 0\n") -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run_check_env(tmp: Path, blast_db: Path, blastdbcmd_body: str) -> subprocess.CompletedProcess:
    stubs = tmp / "bin"
    stubs.mkdir()
    for name in (
        "gcc", "make", "dos2unix", "git",
        "blastn", "makeblastdb", "bowtie2", "bowtie2-build", "samtools",
        "velveth", "velvetg",
    ):
        _stub(stubs, name)
    _stub(stubs, "blastdbcmd", blastdbcmd_body)
    env = os.environ.copy()
    env["PATH"] = str(stubs) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(tmp / "home")
    env["BLAST_DB"] = str(blast_db)
    env["DB"] = "ptv"
    env["ASSEMBLER"] = "velvet"
    env.pop("GENEIN_ENV_DIR", None)
    env.pop("GENEIN_BUNDLE_DIR", None)
    env["GENEIN_CONFIG_FILE"] = str(tmp / "missing.env")
    return subprocess.run(
        ["bash", str(ROOT / "scripts/ops/check_env.sh")],
        cwd=str(tmp), env=env, text=True, capture_output=True, check=False,
    )


class CheckEnvBlastIntegrityTests(unittest.TestCase):
    def test_crashed_blastdbcmd_does_not_print_success(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            prefix = tmp / "blastdb" / "ptv"
            prefix.parent.mkdir(parents=True)
            (tmp / "blastdb" / "ptv.nin").write_bytes(b"junk-index")
            result = _run_check_env(
                tmp, prefix, "#!/bin/sh\nkill -SEGV $$\n",
            )
            text = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, text)
            self.assertNotIn("CONCLUÍDO COM SUCESSO", text)
            self.assertIn("inválido ou corrompido", text)
            self.assertIn("Invalid or corrupt", text)

    def test_invalid_manifest_json_does_not_print_success(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            prefix = tmp / "blastdb" / "ptv"
            prefix.parent.mkdir(parents=True)
            (tmp / "blastdb" / "ptv.nin").write_bytes(b"index")
            (tmp / "blastdb" / "ptv.db-manifest.json").write_text("{garbage", encoding="utf-8")
            result = _run_check_env(
                tmp, prefix, "#!/bin/sh\necho ok\nexit 0\n",
            )
            text = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, text)
            self.assertNotIn("CONCLUÍDO COM SUCESSO", text)
            self.assertIn("inválido ou corrompido", text)
            self.assertIn("JSON inválido", text)


if __name__ == "__main__":
    unittest.main()
