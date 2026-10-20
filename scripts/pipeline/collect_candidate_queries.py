#!/usr/bin/env python3
"""Union assembled sequences and short/read rescue queries with provenance.

Contig IDs are preserved for assembly concordance. Additional exact sequences
reuse an existing query; no reverse complement conversion changes coordinates.
Read occurrence counts are provenance, never independent-template support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from input_validation import iter_fasta, iter_fastq
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evidence"))
from common import sha256_file, write_json_atomic, write_text_atomic


def collect(contigs: Path, short_fasta: Path | None = None,
            fastqs: list[Path] | None = None, rescue_fasta: Path | None = None,
            rescue_candidates: Path | None = None):
    sequences = {}
    sequence_to_id = {}
    metadata = {}
    inputs = []

    def add(name, sequence, kind, preserve_id=False):
        sequence = sequence.upper()
        if not sequence or set(sequence) - set("ACGTRYSWKMBDHVN"):
            raise ValueError(f"Invalid nucleotide query: {name}")
        digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
        query_id = name if preserve_id else sequence_to_id.get(sequence, f"gir_{digest}")
        if query_id in sequences and sequences[query_id] != sequence:
            raise ValueError(f"Query ID collision: {query_id}")
        sequences[query_id] = sequence
        sequence_to_id.setdefault(sequence, query_id)
        entry = metadata.setdefault(query_id, {"length_bp": len(sequence),
            "sequence_sha256": digest, "source_counts": {}})
        entry["source_counts"][kind] = entry["source_counts"].get(kind, 0) + 1

    def fasta(path, kind, preserve_id=False):
        inputs.append({"path": str(path.resolve()), "kind": kind, "sha256": sha256_file(path)})
        if path.stat().st_size:
            for name, sequence in iter_fasta(path):
                add(name, sequence, kind, preserve_id)

    fasta(contigs, "contig", True)
    if short_fasta is not None:
        fasta(short_fasta, "assembled_short")
    for path in fastqs or []:
        inputs.append({"path": str(path.resolve()), "kind": "short_read",
                       "sha256": sha256_file(path)})
        for name, sequence in iter_fastq(path):
            if 20 <= len(sequence) <= 100:
                add(name, sequence, "short_read")
    if rescue_fasta is not None:
        if rescue_candidates is None:
            raise ValueError("rescue FASTA requires its candidate selection table")
        with rescue_candidates.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames or "qseqid" not in reader.fieldnames:
                raise ValueError("rescue selection table requires qseqid")
            hit_ids = {row["qseqid"] for row in reader}
        inputs.extend({"path": str(path.resolve()), "kind": kind, "sha256": sha256_file(path)}
                      for path, kind in ((rescue_fasta, "rescue_read"), (rescue_candidates, "rescue_candidate_selection")))
        found = set()
        for name, sequence in iter_fasta(rescue_fasta):
            if name in hit_ids:
                add(name, sequence, "rescue_read")
                found.add(name)
        if found != hit_ids:
            raise ValueError("rescue selection contains query IDs absent from rescue FASTA")
    return sequences, {"schema_version": "1.0", "deduplication": "exact_same_orientation",
                       "count_unit": "source_occurrence_not_independent_template",
                       "inputs": inputs, "queries": metadata}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contigs", type=Path, required=True)
    parser.add_argument("--short-fasta", type=Path)
    parser.add_argument("--fastq", type=Path, action="append", default=[])
    parser.add_argument("--rescue-fasta", type=Path)
    parser.add_argument("--rescue-candidates", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--supplement-out", type=Path,
                        help="Only short queries and rescue queries; longer contigs retain their existing search")
    args = parser.parse_args()
    sequences, manifest = collect(args.contigs, args.short_fasta, args.fastq,
                                  args.rescue_fasta, args.rescue_candidates)
    write_text_atomic(args.out, "".join(f">{name}\n{seq}\n" for name, seq in sequences.items()))
    write_json_atomic(args.manifest, manifest)
    if args.supplement_out:
        write_text_atomic(args.supplement_out, "".join(
            f">{name}\n{seq}\n" for name, seq in sequences.items()
            if len(seq) <= 100 or "contig" not in manifest["queries"][name]["source_counts"]))


if __name__ == "__main__":
    main()
