#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import tempfile
from pathlib import Path


LENGTHS = (20, 29, 30, 49, 50, 79, 80, 99, 100, 200)
CATEGORIES = ("TARGET_VIRUS", "NEAR_NON_TARGET_VIRUS", "HOST", "VECTOR_ADAPTER", "KNOWN_CONTAMINANT", "LOW_COMPLEXITY")
LIBRARIES = ("shotgun", "amplicon", "targeted", "umi")


def sequence(length: int, category: str, rng: random.Random) -> str:
    if category == "LOW_COMPLEXITY":
        return ("AAAAAC" * ((length + 5) // 6))[:length]
    bases = list(("ACGTGCTA" * ((length + 7) // 8))[:length])
    offsets = {name: index for index, name in enumerate(CATEGORIES)}[category]
    for position in range(offsets, length, 17):
        bases[position] = "ACGT"[("ACGT".index(bases[position]) + offsets) % 4]
    if category == "NEAR_NON_TARGET_VIRUS":
        for _ in range(max(1, length // 40)):
            position = rng.randrange(length)
            bases[position] = "ACGT"[("ACGT".index(bases[position]) + 1) % 4]
    return "".join(bases)


def atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle: handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def generate(out: Path, seed: int = 20260711) -> dict:
    rng = random.Random(seed)
    fasta, rows = [], []
    for length in LENGTHS:
        for category in CATEGORIES:
            identifier = f"synthetic_{category.lower()}_{length}bp"
            seq = sequence(length, category, rng)
            fasta.extend([f">{identifier}", seq])
            rows.append({
                "fixture_id": identifier, "length_bp": length, "category": category,
                "blast_route": "blastn-short" if length < 30 else ("dual" if length < 50 else "blastn"),
                "expected_evidence_ceiling": "EXPLORATORY_FRAGMENT" if length < 50 else "LOCUS_CANDIDATE",
                "sha256": hashlib.sha256(seq.encode()).hexdigest(),
            })
    atomic(out / "short_fragment_matrix.fasta", "\n".join(fasta) + "\n")
    fields = list(rows[0])
    buffer = ["\t".join(fields)] + ["\t".join(str(row[field]) for field in fields) for row in rows]
    atomic(out / "short_fragment_matrix.tsv", "\n".join(buffer) + "\n")
    scenarios = [
        {"scenario_id": f"synthetic_{library}_{control}", "library_mode": library,
         "control_simulation": control, "uses_real_sample": False}
        for library in LIBRARIES for control in ("none", "negative", "positive", "index_switching")
    ]
    atomic(out / "scenario_matrix.json", json.dumps({"seed": seed, "scenarios": scenarios}, indent=2, sort_keys=True) + "\n")
    return {"sequences": len(rows), "scenarios": len(scenarios), "seed": seed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic, non-biological Evidence V2 benchmark fixtures")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260711)
    args = parser.parse_args()
    print(json.dumps(generate(args.out, args.seed), sort_keys=True))


if __name__ == "__main__":
    main()
