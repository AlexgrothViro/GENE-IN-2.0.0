"""Software identity that remains available in a package without a Git checkout."""
from __future__ import annotations

from pathlib import Path
import subprocess


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
