"""Software identity that remains available in a package without a Git checkout."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tomllib


def source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def source_commit(root: Path | None = None) -> str:
    """Return the Git commit of this source tree.

    A checkout uses ``git rev-parse``. A packaged tree has no ``.git`` and
    reads the first line of ``SOURCE_COMMIT``, written when the archive is built.
    """
    root = (root or source_root()).resolve()
    if (root / ".git").exists():
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            completed = None
        if completed is not None:
            sha = completed.stdout.strip()
            if sha:
                return sha
    stamped = root / "SOURCE_COMMIT"
    if stamped.is_file():
        line = stamped.read_text(encoding="utf-8").strip().splitlines()
        if line and line[0].strip():
            return line[0].strip()
    return "unavailable"


def software_version(root: Path | None = None) -> str:
    """Return the distribution version, not the frozen Evidence contract.

    ``VERSION`` stays ``2.0.0-alpha.2`` because that file is the evidence
    contract. ``RELEASE.json`` and ``pyproject.toml`` name the software.
    """
    root = (root or source_root()).resolve()
    release = root / "RELEASE.json"
    if release.is_file():
        try:
            value = json.loads(release.read_text(encoding="utf-8")).get("software_version")
        except (OSError, json.JSONDecodeError):
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    project = root / "pyproject.toml"
    if project.is_file():
        try:
            value = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["version"]
        except (OSError, tomllib.TOMLDecodeError, KeyError):
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unavailable"
