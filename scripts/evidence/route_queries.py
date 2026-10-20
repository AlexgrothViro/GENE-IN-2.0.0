#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .common import read_fasta
except ImportError:
    from common import read_fasta


def write_fasta(path: Path, records: list[tuple[str, str]]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n")
            for offset in range(0, len(sequence), 80):
                handle.write(sequence[offset:offset + 80] + "\n")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Route queries to BLAST tasks by explicit length boundaries")
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    groups = {"lt30": [], "30to49": [], "ge50": []}
    for name, sequence in read_fasta(args.fasta).items():
        if len(sequence) < 30:
            groups["lt30"].append((name, sequence))
        elif len(sequence) < 50:
            groups["30to49"].append((name, sequence))
        else:
            groups["ge50"].append((name, sequence))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for group, records in groups.items():
        write_fasta(out_dir / f"queries_{group}.fa", records)
    print("\n".join(f"{name}\t{len(records)}" for name, records in groups.items()))


if __name__ == "__main__":
    main()
