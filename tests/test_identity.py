"""Commit identity for a Git checkout and for a package without .git."""
from pathlib import Path

import pytest

from genein.identity import software_version, source_commit


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    not (ROOT / ".git").exists(),
    reason="Pacote distribuído não traz .git; a identidade fica em SOURCE_COMMIT.",
)
def test_checkout_reports_head():
    import subprocess
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    assert source_commit(ROOT) == head


def test_package_without_git_reads_source_commit_file(tmp_path):
    (tmp_path / "SOURCE_COMMIT").write_text("53af26ba439ab29bff013bde131eb5ae9eca3cb6\n", encoding="utf-8")
    assert source_commit(tmp_path) == "53af26ba439ab29bff013bde131eb5ae9eca3cb6"


def test_missing_identity_is_explicit(tmp_path):
    assert source_commit(tmp_path) == "unavailable"
    assert software_version(tmp_path) == "unavailable"


def test_distribution_version_is_not_the_evidence_contract():
    assert software_version(ROOT) == "2.0.1"
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0-alpha.2"
