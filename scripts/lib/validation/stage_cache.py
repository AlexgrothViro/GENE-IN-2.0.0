"""Stage artifact cache for optimization-pipeline reuse."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def cache_key(*parts: str) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def cache_dir(root: Path, sample_id: str, stage: str, key: str) -> Path:
    return root / "cache" / sample_id / stage / key


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def reuse_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        return
    shutil.copy2(source, target)
