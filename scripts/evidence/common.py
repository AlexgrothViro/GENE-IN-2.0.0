#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator


SHA256_HEX_LENGTH = 64


def blast_db_arg(database: str | Path) -> str:
    """Value to pass as BLAST+ -db so a path containing whitespace is taken
    as one database instead of the whitespace-separated multi-database list
    BLAST+'s own argument parser otherwise assumes. This affects the -db
    argument value itself (both via subprocess argv lists and via a shell),
    not the shell's own quoting, which already preserves the path intact.
    """
    text = str(database)
    return f'"{text}"' if any(character.isspace() for character in text) else text


def configure_csv_field_limit() -> None:
    """Allow long query/interval lists without truncating evidence fields."""
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            # Some Python builds accept only a C long (32 bits on Windows).
            limit //= 10


def read_tsv(path: str | Path) -> list[dict[str, str]]:
    return list(iter_tsv(path))


def iter_tsv(path: str | Path) -> Iterator[dict[str, str]]:
    """Read rows with the same validation and ordering without retaining the table."""
    configure_csv_field_limit()
    with Path(path).open("r", encoding="utf-8", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"TSV has no header: {path}")
        yield from reader


def _atomic_target(path: Path) -> tuple[Path, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    return Path(tmp_name), os.fdopen(fd, "w", encoding="utf-8", newline="")


def fsync_directory(path: str | Path) -> None:
    """Durably persist directory metadata where the platform supports it."""
    directory = Path(path)
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_file(path: str | Path) -> None:
    """Durably persist an existing file on POSIX and Windows."""
    # The Windows CRT rejects fsync() on a read-only descriptor (EBADF).
    mode = "rb+" if os.name == "nt" else "rb"
    with Path(path).open(mode) as handle:
        os.fsync(handle.fileno())


def _flush_and_sync(handle: object) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def replace_atomic(source: str | Path, target: str | Path, *, attempts: int = 40) -> None:
    """Replace a file atomically, tolerating transient Windows reader locks."""
    source_path = Path(source)
    target_path = Path(target)
    for attempt in range(attempts):
        try:
            os.replace(source_path, target_path)
            return
        except PermissionError:
            if os.name != "nt" or attempt + 1 >= attempts:
                raise
            time.sleep(min(0.005 * (attempt + 1), 0.1))


def write_tsv_atomic(path: str | Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    target = Path(path)
    tmp, handle = _atomic_target(target)
    try:
        with handle:
            writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: row.get(name, "") for name in fieldnames})
            _flush_and_sync(handle)
        replace_atomic(tmp, target)
        fsync_directory(target.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_json_atomic(path: str | Path, value: object) -> None:
    target = Path(path)
    tmp, handle = _atomic_target(target)
    try:
        with handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            _flush_and_sync(handle)
        replace_atomic(tmp, target)
        fsync_directory(target.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_text_atomic(path: str | Path, value: str) -> None:
    target = Path(path)
    tmp, handle = _atomic_target(target)
    try:
        with handle:
            handle.write(value)
            _flush_and_sync(handle)
        replace_atomic(tmp, target)
        fsync_directory(target.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_fasta(path: str | Path) -> dict[str, str]:
    sequences: dict[str, str] = {}
    current: str | None = None
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                current = line[1:].split()[0]
                if not current or current in sequences:
                    raise ValueError(f"invalid or duplicate FASTA identifier: {current!r}")
                sequences[current] = ""
            elif current is None:
                raise ValueError("FASTA sequence found before first header")
            else:
                sequences[current] += line.upper()
    return sequences


def merge_intervals(intervals: Iterable[tuple[int, int]], gap: int = 0) -> list[tuple[int, int]]:
    normalized = sorted((min(a, b), max(a, b)) for a, b in intervals)
    merged: list[list[int]] = []
    for start, end in normalized:
        if not merged or start > merged[-1][1] + gap + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def interval_size(intervals: Iterable[tuple[int, int]]) -> int:
    return sum(end - start + 1 for start, end in merge_intervals(intervals))


def format_intervals(intervals: Iterable[tuple[int, int]]) -> str:
    return ";".join(f"{a}-{b}" for a, b in merge_intervals(intervals))


def parse_intervals(value: str) -> list[tuple[int, int]]:
    result = []
    for item in filter(None, value.split(";")):
        left, right = item.split("-", 1)
        result.append((int(left), int(right)))
    return result


def sequence_metrics(sequence: str) -> dict[str, float]:
    seq = sequence.upper()
    if not seq:
        return {"entropy": 0.0, "n_fraction": 0.0, "max_homopolymer_fraction": 0.0}
    counts = Counter(base for base in seq if base in "ACGT")
    valid = sum(counts.values())
    entropy = 0.0
    if valid:
        entropy = -sum((count / valid) * math.log2(count / valid) for count in counts.values())
    longest = 1
    run = 1
    for previous, current in zip(seq, seq[1:]):
        run = run + 1 if current == previous else 1
        longest = max(longest, run)
    return {
        "entropy": entropy,
        "n_fraction": seq.count("N") / len(seq),
        "max_homopolymer_fraction": longest / len(seq),
    }


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_manifest(directory: str | Path, *, exclude: set[str] | None = None) -> dict:
    root = Path(directory)
    excluded = {"SUCCESS.json", "artifact_manifest.json"} if exclude is None else exclude
    files = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded or path.name.startswith(".") or path.name.endswith(".tmp"):
            continue
        files[relative] = {"size": path.stat().st_size, "sha256": sha256_file(path)}
    return {"schema_version": "1.0", "files": files}


def validate_artifact_manifest(
    directory: str | Path, manifest: dict, *, exclude: set[str] | None = None
) -> list[str]:
    root = Path(directory)
    errors: list[str] = []
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        return ["artifact manifest schema is invalid"]
    if set(manifest) != {"schema_version", "files"}:
        return ["artifact manifest fields are invalid"]
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict) or not files:
        return ["artifact manifest is empty or invalid"]
    excluded = {"SUCCESS.json", "artifact_manifest.json"} if exclude is None else exclude
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).as_posix() not in excluded
        and not path.name.startswith(".")
        and not path.name.endswith(".tmp")
    }
    declared_files = set(files)
    for relative in sorted(actual_files - declared_files):
        errors.append(f"artifact is missing from manifest: {relative}")
    for relative in sorted(declared_files - actual_files):
        errors.append(f"manifest declares an unexpected artifact: {relative}")
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, dict):
            errors.append(f"invalid artifact manifest entry: {relative!r}")
            continue
        relative_path = Path(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or relative_path.as_posix() != relative
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        ):
            errors.append(f"invalid artifact manifest path: {relative!r}")
            continue
        if set(expected) != {"size", "sha256"}:
            errors.append(f"invalid artifact manifest metadata: {relative}")
            continue
        expected_size = expected.get("size")
        expected_sha256 = expected.get("sha256")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            errors.append(f"invalid artifact size metadata: {relative}")
            continue
        if (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != SHA256_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in expected_sha256)
        ):
            errors.append(f"invalid artifact hash metadata: {relative}")
            continue
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            errors.append(f"artifact escapes run directory: {relative}")
            continue
        if not path.is_file():
            errors.append(f"manifest artifact is missing: {relative}")
            continue
        if path.stat().st_size != expected.get("size"):
            errors.append(f"artifact size mismatch: {relative}")
        if sha256_file(path) != expected.get("sha256"):
            errors.append(f"artifact hash mismatch: {relative}")
    return errors


def as_int(value: str | int | float | None, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: str | int | float | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
