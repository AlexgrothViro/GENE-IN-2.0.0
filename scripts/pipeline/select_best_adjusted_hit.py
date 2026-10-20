#!/usr/bin/env python3
"""Select one adjusted-identity record deterministically without SIGPIPE-prone pipes."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


REQUIRED_FIELDS = (
    "qseqid", "sseqid", "pident", "length", "evalue", "bitscore",
    "qlen", "aln_cov", "adj_identity",
)


def finite_number(value: str, field: str, line_number: int) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid numeric field {field!r} at line {line_number}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite numeric field {field!r} at line {line_number}")
    return number


def select_best(path: Path) -> str:
    try:
        if path.stat().st_size == 0:
            raise ValueError("adjusted-identity TSV is empty")
        with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames != list(REQUIRED_FIELDS):
                raise ValueError("adjusted-identity TSV has an invalid header")
            best: tuple[float, tuple[str, ...], dict[str, str], float] | None = None
            for line_number, row in enumerate(reader, start=2):
                coverage = finite_number(row["aln_cov"], "aln_cov", line_number)
                adjusted = finite_number(row["adj_identity"], "adj_identity", line_number)
                tie_breaker = tuple(row[field] for field in REQUIRED_FIELDS)
                candidate = (-adjusted, tie_breaker, row, coverage)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
    except OSError as exc:
        raise OSError(f"cannot read adjusted-identity TSV: {path}: {exc}") from exc
    if best is None:
        return ""
    row = best[2]
    coverage = best[3]
    return (
        f"{row['qseqid']} vs {row['sseqid']} | "
        f"adj_identity={row['adj_identity']}% | cobertura={coverage * 100:.2f}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tsv", type=Path)
    args = parser.parse_args()
    result = select_best(args.tsv)
    if result:
        print(result)


if __name__ == "__main__":
    main()
