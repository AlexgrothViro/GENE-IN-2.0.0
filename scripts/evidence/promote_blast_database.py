#!/usr/bin/env python3
"""Validate and atomically activate a complete BLAST database generation."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import blast_db_arg, fsync_directory, sha256_file, write_json_atomic
except ImportError:
    from common import blast_db_arg, fsync_directory, sha256_file, write_json_atomic


def run_checked(command: list[str], description: str, *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=cwd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{description} failed: {detail}")


def produced_files(prefix: Path) -> list[Path]:
    files = sorted(path for path in prefix.parent.glob(f"{prefix.name}.*") if path.is_file())
    if not files or any(path.stat().st_size == 0 for path in files):
        raise ValueError("makeblastdb produced no complete non-empty file set")
    return files


def restore_bytes(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    rollback = path.parent / f".{path.name}.rollback.{uuid.uuid4().hex}"
    rollback.write_bytes(previous)
    if os.name != "nt":
        with rollback.open("rb") as handle:
            os.fsync(handle.fileno())
    os.replace(rollback, path)


@contextmanager
def promotion_lock(destination: Path):
    lock_path = destination.parent / f".{destination.name}.promotion.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def alias_points_to(alias_path: Path, expected_alias: bytes) -> bool:
    """Confirm that the active alias is the validated alias just generated."""
    return alias_path.read_bytes() == expected_alias


def promote(build_dir: Path, destination: Path, reference: Path,
            blastdbcmd: str, alias_tool: str, manifest_path: Path,
            index_manifest_source: Path | None = None) -> dict:
    build_dir = build_dir.resolve()
    destination = destination.resolve()
    reference = reference.resolve()
    if build_dir.parent.stat().st_dev != destination.parent.stat().st_dev:
        raise ValueError("BLAST staging and destination must be on the same filesystem")
    build_prefix = build_dir / destination.name
    files = produced_files(build_prefix)
    run_checked([blastdbcmd, "-db", blast_db_arg(build_prefix), "-info"], "temporary BLAST database validation")
    index_manifest = None
    if index_manifest_source is not None:
        index_manifest = json.loads(index_manifest_source.read_text(encoding="utf-8", errors="strict"))

    generation_root = destination.parent / f".{destination.name}.generations"
    generation_root.mkdir(parents=True, exist_ok=True)
    generation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    generation_dir = generation_root / generation_id
    generation_manifest = {
        "schema_version": "1.0",
        "logical_prefix": str(destination),
        "generation_id": generation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_fasta": {
            "path": str(reference), "size": reference.stat().st_size,
            "sha256": sha256_file(reference),
        },
        "produced_files": {
            path.name: {"size": path.stat().st_size, "sha256": sha256_file(path)}
            for path in files
        },
    }
    write_json_atomic(build_dir / "generation_manifest.json", generation_manifest)
    if os.name != "nt":
        for path in build_dir.iterdir():
            if path.is_file():
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
    fsync_directory(build_dir)
    os.replace(build_dir, generation_dir)
    fsync_directory(generation_root)

    generation_prefix = generation_dir / destination.name
    alias_prefix = destination.parent / f".{destination.name}.alias.{uuid.uuid4().hex}"
    alias_path = Path(f"{alias_prefix}.nal")
    final_alias = Path(f"{destination}.nal")
    with promotion_lock(destination):
        previous_alias = final_alias.read_bytes() if final_alias.is_file() else None
        previous_manifest = manifest_path.read_bytes() if manifest_path.is_file() else None
        index_manifest_path = Path(f"{destination}.index-manifest.json")
        previous_index_manifest = index_manifest_path.read_bytes() if index_manifest_path.is_file() else None
        activated = False
        try:
            run_checked([
                alias_tool, "-dbtype", "nucl", "-dblist", blast_db_arg(generation_prefix.relative_to(destination.parent)),
                "-out", alias_prefix.name, "-title", f"Gene-In {destination.name} {generation_id}",
            ], "BLAST alias creation", cwd=destination.parent)
            run_checked([blastdbcmd, "-db", blast_db_arg(alias_prefix), "-info"], "BLAST alias validation")
            if os.name != "nt":
                with alias_path.open("rb") as handle:
                    os.fsync(handle.fileno())
            generated_alias = alias_path.read_bytes()
            os.replace(alias_path, final_alias)
            fsync_directory(destination.parent)
            activated = True
            run_checked([blastdbcmd, "-db", blast_db_arg(destination), "-info"], "promoted BLAST database validation")
            write_json_atomic(manifest_path, generation_manifest)
            if index_manifest is not None:
                write_json_atomic(index_manifest_path, index_manifest)

            try:
                if not alias_points_to(final_alias, generated_alias):
                    raise RuntimeError("active BLAST alias no longer points to this generation")
                preserved = {final_alias.resolve(), manifest_path.resolve(), Path(f"{destination}.index-manifest.json").resolve()}
                for path in destination.parent.glob(f"{destination.name}.*"):
                    if path.is_file() and path.resolve() not in preserved:
                        path.unlink()
                for old_generation in generation_root.iterdir():
                    if old_generation.is_dir() and old_generation != generation_dir:
                        shutil.rmtree(old_generation, ignore_errors=True)
                fsync_directory(destination.parent)
            except OSError:
                # Cleanup is non-transactional housekeeping after a validated commit;
                # it must never roll back or invalidate the newly active database.
                pass
            return generation_manifest
        except Exception:
            alias_path.unlink(missing_ok=True)
            if activated:
                restore_bytes(final_alias, previous_alias)
                restore_bytes(manifest_path, previous_manifest)
                restore_bytes(index_manifest_path, previous_index_manifest)
                fsync_directory(destination.parent)
            shutil.rmtree(generation_dir, ignore_errors=True)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--index-manifest-source", type=Path)
    parser.add_argument("--blastdbcmd", default="blastdbcmd")
    parser.add_argument("--alias-tool", default="blastdb_aliastool")
    args = parser.parse_args()
    result = promote(
        args.build_dir, args.destination, args.reference, args.blastdbcmd,
        args.alias_tool, args.manifest, args.index_manifest_source,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
