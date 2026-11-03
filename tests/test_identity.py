"""Commit identity for a Git checkout and for a package without .git."""
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from genein.identity import software_version, source_commit


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("payload", [[], None, 42, "invalid"])
def test_non_object_release_keeps_identity_fallback(tmp_path, payload):
    (tmp_path / "RELEASE.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="2.0.2"\n', encoding="utf-8")
    assert source_commit(tmp_path) == "unavailable"
    assert software_version(tmp_path) == "2.0.2"


@pytest.mark.parametrize("stamp", ["$Format:%H$", "not-a-commit", "", "123456"])
def test_invalid_stamp_falls_back_to_release_commit(tmp_path, stamp):
    expected = "af7cb088b3013df07fd3abfaa23ba89dba42cf6b"
    (tmp_path / "SOURCE_COMMIT").write_text(stamp, encoding="utf-8")
    (tmp_path / "RELEASE.json").write_text(json.dumps({"source_commit": expected}), encoding="utf-8")
    assert source_commit(tmp_path) == expected


def test_source_stamp_takes_precedence_over_release(tmp_path):
    expected = "42a2c135666337b025b9cd1cdde5b8ae208831f6"
    (tmp_path / "SOURCE_COMMIT").write_text(expected + "\n", encoding="utf-8")
    (tmp_path / "RELEASE.json").write_text(json.dumps({"source_commit": "a" * 40}), encoding="utf-8")
    assert source_commit(tmp_path) == expected


def test_invalid_release_json_keeps_fallback(tmp_path):
    (tmp_path / "RELEASE.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="2.0.2"\n', encoding="utf-8")
    assert source_commit(tmp_path) == "unavailable"
    assert software_version(tmp_path) == "2.0.2"


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="git archive requires a Git checkout")
def test_git_archive_records_head(tmp_path):
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    blob = subprocess.check_output(["git", "-C", str(ROOT), "archive", "HEAD", "SOURCE_COMMIT"])
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        stamp = archive.extractfile("SOURCE_COMMIT").read()
    (tmp_path / "SOURCE_COMMIT").write_bytes(stamp)
    assert source_commit(tmp_path) == head


@pytest.mark.skipif(
    not (ROOT / ".git").exists(),
    reason="Pacote distribuído não traz .git; a identidade fica em SOURCE_COMMIT.",
)
def test_checkout_reports_head():
    import subprocess
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    assert source_commit(ROOT) == head


def test_package_without_git_reads_source_commit_file(tmp_path):
    (tmp_path / "SOURCE_COMMIT").write_text("42a2c135666337b025b9cd1cdde5b8ae208831f6\n", encoding="utf-8")
    assert source_commit(tmp_path) == "42a2c135666337b025b9cd1cdde5b8ae208831f6"


def test_missing_identity_is_explicit(tmp_path):
    assert source_commit(tmp_path) == "unavailable"
    assert software_version(tmp_path) == "unavailable"


def test_distribution_version_is_not_the_evidence_contract():
    assert software_version(ROOT) == "2.0.2"
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0-alpha.2"


def test_provenance_writer_records_distribution_identity():
    import sys
    sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
    from write_provenance import distribution_identity

    identity = distribution_identity()
    assert identity == {"software_version": "2.0.2", "source_commit": source_commit(ROOT)}
    writer = (ROOT / "scripts" / "evidence" / "write_provenance.py").read_text(encoding="utf-8")
    assert '"pipeline_version": "2.0.0-alpha.2"' in writer
