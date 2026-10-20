#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import fsync_directory, fsync_file, read_fasta, read_tsv, sha256_file, write_json_atomic
except ImportError:
    from common import fsync_directory, fsync_file, read_fasta, read_tsv, sha256_file, write_json_atomic


REQUIRED_CATEGORIES = {
    "TARGET_VIRUS", "NEAR_NON_TARGET_VIRUS", "HOST", "VECTOR_ADAPTER",
    "KNOWN_CONTAMINANT", "SYNTHETIC_SEQUENCE",
}


def tool_version(command: str) -> dict[str, str]:
    executable = shutil.which(command)
    if not executable:
        return {"executable": "UNAVAILABLE", "version": "UNAVAILABLE", "sha256": "UNAVAILABLE"}
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    text = (result.stdout or result.stderr).splitlines()
    return {
        "executable": str(Path(executable).resolve()), "version": text[0] if text else "UNKNOWN",
        "sha256": sha256_file(executable),
    }


def promote_directory(staging: Path, final: Path) -> None:
    os.replace(staging, final)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and atomically promote a complete competitive panel")
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--panel-id", required=True)
    args = parser.parse_args()
    if args.final.exists():
        raise FileExistsError(f"panel already exists: {args.final}")
    if args.final.name != args.panel_id:
        raise ValueError("final panel directory must match panel_id")
    if (args.staging / "SUCCESS.json").exists():
        raise ValueError("panel staging contains an invalid pre-existing SUCCESS.json")
    (args.staging / "panel_manifest.json").unlink(missing_ok=True)
    args.final.parent.mkdir(parents=True, exist_ok=True)
    if args.staging.stat().st_dev != args.final.parent.stat().st_dev:
        raise ValueError("panel staging and final directory must share a filesystem")
    fasta = args.staging / "panel.fa"
    labels = args.staging / "labels.tsv"
    sequences = read_fasta(fasta)
    label_rows = read_tsv(labels)
    if not label_rows or {row.get("sseqid") for row in label_rows} != set(sequences):
        raise ValueError("panel labels do not match FASTA identifiers")
    categories = {row.get("category") for row in label_rows}
    missing_categories = REQUIRED_CATEGORIES - categories
    if missing_categories:
        raise ValueError("competitive panel missing categories: " + ", ".join(sorted(missing_categories)))
    blast_files = [args.staging / "blast" / f"panel.{ext}" for ext in ("nhr", "nin", "nsq")]
    if any(not path.is_file() or path.stat().st_size == 0 for path in blast_files):
        raise ValueError("incomplete BLAST database")
    bt2 = [args.staging / "bowtie2" / f"panel.{ext}.bt2" for ext in ("1", "2", "3", "4", "rev.1", "rev.2")]
    bt2l = [args.staging / "bowtie2" / f"panel.{ext}.bt2l" for ext in ("1", "2", "3", "4", "rev.1", "rev.2")]
    index_files = bt2 if all(path.is_file() and path.stat().st_size for path in bt2) else bt2l
    if not all(path.is_file() and path.stat().st_size for path in index_files):
        raise ValueError("incomplete Bowtie2 index")
    partials = [
        path for path in args.staging.rglob("*")
        if path.is_file() and (path.name.startswith(".") or path.name.endswith(".tmp"))
    ]
    if partials:
        raise ValueError("temporary panel artifacts remain: " + ", ".join(path.name for path in partials))
    files = sorted(
        path for path in args.staging.rglob("*")
        if path.is_file() and path.name not in {"SUCCESS.json", "panel_manifest.json"}
    )
    if not files:
        raise ValueError("competitive panel has no artifacts")
    for path in files:
        fsync_file(path)
    manifest = {
        "schema_version": "2.0", "panel_id": args.panel_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "sequence_count": len(sequences),
        "categories": sorted(categories), "index_kind": index_files[0].suffix.lstrip("."),
        "constructors": {"makeblastdb": tool_version("makeblastdb"), "bowtie2-build": tool_version("bowtie2-build")},
        "files": {
            str(path.relative_to(args.staging)): {"size": path.stat().st_size, "sha256": sha256_file(path)}
            for path in files
        },
    }
    write_json_atomic(args.staging / "panel_manifest.json", manifest)
    success = {
        "panel_id": args.panel_id, "status": "done", "shadow_mode": False,
        "manifest": "panel_manifest.json", "manifest_sha256": sha256_file(args.staging / "panel_manifest.json"),
    }
    fsync_directory(args.staging)
    try:
        promote_directory(args.staging, args.final)
    except Exception:
        (args.staging / "panel_manifest.json").unlink(missing_ok=True)
        fsync_directory(args.staging)
        raise
    fsync_directory(args.final.parent)
    try:
        # The promoted panel is consumable only after this final commit write.
        write_json_atomic(args.final / "SUCCESS.json", success)
        fsync_directory(args.final)
    except Exception:
        (args.final / "SUCCESS.json").unlink(missing_ok=True)
        fsync_directory(args.final)
        try:
            promote_directory(args.final, args.staging)
            (args.staging / "panel_manifest.json").unlink(missing_ok=True)
            fsync_directory(args.final.parent)
        except Exception:
            pass
        raise
    print(args.final)


if __name__ == "__main__":
    main()
