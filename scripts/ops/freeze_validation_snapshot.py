#!/usr/bin/env python3
"""Create a deterministic checksum manifest from a canonical, already frozen v1.1 tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


EXCLUDED_PARTS = {".git", "data", "results", "logs", "tmp", "__pycache__", ".pytest_cache"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a canonical Gene-In v1.1 source tree as a SHA-256 manifest")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-version", default="1.1")
    args = parser.parse_args()
    root = args.source.resolve()
    version_path = root / "VERSION"
    if not version_path.is_file():
        raise SystemExit("[FATAL] canonical source has no VERSION file")
    version = version_path.read_text(encoding="utf-8").strip()
    if not version.startswith(args.expected_version):
        raise SystemExit(f"[FATAL] refusing to label version {version!r} as {args.expected_version}")
    output = args.out.resolve()
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts):
            continue
        if path.resolve() == output:
            continue
        files.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)})
    manifest = {
        "schema": "gene-in-validation-snapshot-1", "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(), "source": str(root),
        "file_count": len(files), "files": files,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    print(output)


if __name__ == "__main__":
    main()
