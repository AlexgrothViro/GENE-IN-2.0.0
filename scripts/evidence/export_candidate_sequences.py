#!/usr/bin/env python3
"""Export every aligned query for human review, independently of its tier."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import read_fasta, iter_tsv, sha256_text, write_json_atomic, write_text_atomic, write_tsv_atomic


def export(queries: Path, manifest_path: Path, fragments: Path, output: Path):
    sequences = read_fasta(queries) if queries.stat().st_size else {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reference_lengths = {}
    for row in iter_tsv(fragments):
        query = row["qseqid"]
        reference_lengths[query] = max(reference_lengths.get(query, 0), int(row.get("slen") or 0))
    selected = sorted(reference_lengths)
    metadata = manifest["queries"]
    for query in selected:
        if query not in sequences or query not in metadata:
            raise ValueError(f"Aligned query missing from candidate bundle: {query}")
        if sha256_text(sequences[query]) != metadata[query]["sequence_sha256"]:
            raise ValueError(f"Candidate sequence hash mismatch: {query}")
        reference_length = reference_lengths[query]
        if reference_length and len(sequences[query]) > reference_length:
            print(f"[AVISO] Sequência candidata {query}: {len(sequences[query])} pb, maior que a maior referência alinhada ({reference_length} pb). Revise os segmentos alinhados e a origem; comprimento não confirma origem viral. Sequência preservada integralmente.", file=sys.stderr)
    output.mkdir(parents=True, exist_ok=True)
    write_text_atomic(output / "candidate_sequences.fa",
                      "".join(f">{query}\n{sequences[query]}\n" for query in selected))
    fields = ["qseqid", "sequence_length_bp", "sequence_sha256", "query_origins",
              "sseqid", "category", "taxon", "task", "aligned_query_bp", "query_coverage",
              "weighted_pident", "best_bitscore", "best_evalue", "assembly_method"]
    rows = ({"qseqid": row["qseqid"], "sequence_length_bp": len(sequences[row["qseqid"]]),
             "sequence_sha256": metadata[row["qseqid"]]["sequence_sha256"],
             "query_origins": ";".join(sorted(metadata[row["qseqid"]]["source_counts"])),
             "aligned_query_bp": row["query_covered_bp"],
             **{key: row.get(key, "") for key in fields if key in row and key != "qseqid"}}
            for row in iter_tsv(fragments))
    write_tsv_atomic(output / "candidate_sequences.tsv", rows, fields)
    write_json_atomic(output / "candidate_queries.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fragments", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    export(args.queries, args.manifest, args.fragments, args.out_dir)


if __name__ == "__main__":
    main()
