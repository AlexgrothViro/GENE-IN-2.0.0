#!/usr/bin/env python3
"""Content-addressed cache metadata for BLAST and Bowtie2 indexes."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

try:
    from .common import sha256_file, write_json_atomic
except ImportError:
    from common import sha256_file, write_json_atomic


SCHEMA_VERSION = "1.0"


def builder_identity(command: str) -> dict[str, str]:
    executable = shutil.which(command)
    if not executable:
        raise RuntimeError(f"index builder is unavailable: {command}")
    version_text = "UNKNOWN"
    options = ("-version", "--version") if command in {"makeblastdb", "blastn", "blastdbcmd"} else ("--version", "-version")
    for option in options:
        result = subprocess.run([executable, option], capture_output=True, text=True, check=False)
        line = (result.stdout or result.stderr).splitlines()
        if result.returncode == 0 and line and not line[0].strip().upper().startswith("USAGE"):
            version_text = line[0].strip()
            break
    return {
        "command": command,
        "executable": str(Path(executable).resolve()),
        "version": version_text,
        "sha256": sha256_file(executable),
    }


def fingerprint(reference: str | Path, builders: list[str]) -> dict:
    path = Path(reference)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"reference FASTA is missing or empty: {path}")
    identities = {name: builder_identity(name) for name in sorted(set(builders))}
    return {
        "schema_version": SCHEMA_VERSION,
        "reference": {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": sha256_file(path)},
        "builders": identities,
    }


def matches(manifest: dict, reference: str | Path, builders: list[str]) -> bool:
    expected = fingerprint(reference, builders)
    return manifest == expected


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an index cache by input content and builder identity")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--builder", action="append", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = fingerprint(args.reference, args.builder)
    if args.write:
        write_json_atomic(args.manifest, expected)
        return
    try:
        actual = json.loads(args.manifest.read_text(encoding="utf-8", errors="strict"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit(1)
    raise SystemExit(0 if actual == expected else 1)


if __name__ == "__main__":
    main()
