#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import tempfile
from pathlib import Path

try:
    from .common import read_fasta, write_tsv_atomic
except ImportError:
    from common import read_fasta, write_tsv_atomic


CATEGORIES = {
    "TARGET_VIRUS", "NEAR_NON_TARGET_VIRUS", "HOST", "VECTOR_ADAPTER",
    "KNOWN_CONTAMINANT", "SYNTHETIC_SEQUENCE",
}


def safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:80]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a labeled competitive FASTA; makeblastdb is run separately")
    parser.add_argument("--source", action="append", required=True, metavar="CATEGORY=FASTA")
    parser.add_argument("--out-fasta", required=True)
    parser.add_argument("--out-labels", required=True)
    args = parser.parse_args()
    fasta_target = Path(args.out_fasta)
    fasta_target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{fasta_target.name}.", suffix=".tmp", dir=fasta_target.parent)
    labels = []
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            seen = set()
            for spec in args.source:
                if "=" not in spec:
                    parser.error("--source must use CATEGORY=FASTA")
                category, path = spec.split("=", 1)
                if category not in CATEGORIES:
                    parser.error(f"invalid competitive category: {category}")
                for original_id, sequence in read_fasta(path).items():
                    digest = hashlib.sha256(f"{category}|{original_id}|{sequence}".encode()).hexdigest()[:12]
                    identifier = f"GI2_{category}_{digest}_{safe_token(original_id)}"
                    if identifier in seen:
                        raise ValueError(f"competitive identifier collision: {identifier}")
                    seen.add(identifier)
                    output.write(f">{identifier}\n")
                    for offset in range(0, len(sequence), 80):
                        output.write(sequence[offset:offset + 80] + "\n")
                    labels.append({"sseqid": identifier, "category": category, "taxon": original_id, "segment": "unsegmented"})
        os.replace(tmp_name, fasta_target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    write_tsv_atomic(args.out_labels, labels, ["sseqid", "category", "taxon", "segment"])


if __name__ == "__main__":
    main()
