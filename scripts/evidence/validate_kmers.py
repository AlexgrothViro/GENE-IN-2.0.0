#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
from pathlib import Path


def first_read_length(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="strict") as handle:
        header = handle.readline()
        sequence = handle.readline().strip()
    if not header.startswith("@") or not sequence:
        raise ValueError("cannot determine FASTQ read length")
    return len(sequence)


def validate(value: str, read_length: int) -> str:
    try:
        kmers = [int(item) for item in value.split(",")]
    except ValueError as exc:
        raise ValueError("k-mers must be comma-separated integers") from exc
    if not kmers or any(k <= 0 or k >= 128 or k % 2 == 0 for k in kmers):
        raise ValueError("all k-mers must be positive, odd, and smaller than 128")
    if kmers != sorted(set(kmers)):
        raise ValueError("k-mers must be unique and strictly increasing")
    if any(k >= read_length for k in kmers):
        raise ValueError(f"all k-mers must be smaller than the observed read length ({read_length})")
    return ",".join(map(str, kmers))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate advanced SPAdes k-mers against actual reads")
    parser.add_argument("--kmers", required=True)
    parser.add_argument("--fastq", required=True, type=Path)
    args = parser.parse_args()
    print(validate(args.kmers, first_read_length(args.fastq)))


if __name__ == "__main__":
    main()
