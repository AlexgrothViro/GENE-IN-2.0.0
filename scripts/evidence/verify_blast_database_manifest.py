#!/usr/bin/env python3
"""Check that the BLAST indexes about to be searched match their recorded manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys

try:
    from .common import sha256_file
except ImportError:
    from common import sha256_file


def verify(prefix: Path, manifest_path: Path | None = None) -> int:
    prefix = prefix.resolve()
    manifest_path = manifest_path or Path(str(prefix) + ".db-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("produced_files")
    if manifest.get("schema_version") != "1.0" or not isinstance(files, dict) or not files:
        raise ValueError("manifesto BLAST inválido ou sem arquivos/hashes")
    parent = prefix.parent
    alias = Path(str(prefix) + ".nal")
    if alias.exists():
        generation = manifest.get("generation_id", "")
        if not isinstance(generation, str) or not generation or Path(generation).name != generation or generation in {".", ".."}:
            raise ValueError("geração BLAST inválida no manifesto")
        parent = prefix.parent / f".{prefix.name}.generations" / generation
        lines = [line.split(None, 1)[1] for line in alias.read_text().splitlines()
                 if line.strip().startswith("DBLIST ")]
        targets = shlex.split(lines[0]) if len(lines) == 1 else []
        if len(targets) != 1 or (prefix.parent / targets[0]).resolve() != (parent / prefix.name).resolve():
            raise ValueError("alias BLAST diverge da geração registrada no manifesto")
    for name, details in files.items():
        if not isinstance(name, str) or Path(name).name != name or not name.startswith(prefix.name + "."):
            raise ValueError("nome de índice BLAST inválido no manifesto")
        if not isinstance(details, dict) or not isinstance(details.get("size"), int) or details["size"] <= 0:
            raise ValueError(f"tamanho não registrado no manifesto: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(details.get("sha256", ""))):
            raise ValueError(f"hash não registrado no manifesto: {name}")
        path = parent / name
        if not path.is_file() or path.stat().st_size != details["size"] or sha256_file(path) != details["sha256"]:
            raise ValueError(f"banco BLAST alterado ou incompleto: {name}; reconstrua o banco e seu manifesto")
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        count = verify(args.prefix, args.manifest)
    except (OSError, ValueError, TypeError) as exc:
        print(f"[FATAL] Integridade do banco BLAST: {exc}", file=sys.stderr)
        return 2
    print(f"[OK] Banco BLAST: {count} arquivos conferidos por tamanho e SHA-256.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
