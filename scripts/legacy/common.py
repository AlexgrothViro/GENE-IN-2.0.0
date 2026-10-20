"""Small path contract shared by legacy test-only utilities."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORK_DIR = Path(os.environ.get("LEGACY_WORK_DIR", REPO_ROOT / "run_T1" / "work")).resolve()


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()
