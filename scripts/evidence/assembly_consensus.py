#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

try:
    from .common import read_fasta, read_tsv, write_json_atomic, write_text_atomic, write_tsv_atomic
except ImportError:
    from common import read_fasta, read_tsv, write_json_atomic, write_text_atomic, write_tsv_atomic


ASSEMBLERS = {"velvet", "spades", "metaspades"}
STATUS_VALUES = {"SUCCESS", "SOFT", "EMPTY", "HARD", "NOT_APPLICABLE"}


def parse_key_values(values: list[str], allowed_keys: set[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        key, separator, value = raw.partition("=")
        if not separator or key not in allowed_keys or not value or key in result:
            raise ValueError(f"invalid {label}: {raw!r}")
        result[key] = value
    return result


def reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]


def canonical_sequence(sequence: str) -> str:
    reverse = reverse_complement(sequence)
    return min(sequence, reverse)


def combine(
    inputs: dict[str, Path],
    statuses: dict[str, str],
    out_fasta: Path,
    out_manifest: Path,
    minimum_successful: int,
    profile_id: str,
) -> dict:
    if minimum_successful < 2:
        raise ValueError("assembly consensus requires at least two successful assemblers")
    if set(inputs) - ASSEMBLERS or set(statuses) - ASSEMBLERS:
        raise ValueError("unknown assembler in consensus input")
    for assembler, status in statuses.items():
        if status not in STATUS_VALUES:
            raise ValueError(f"invalid assembler status: {assembler}={status}")

    sequence_sources: dict[str, list[dict]] = defaultdict(list)
    for assembler in sorted(inputs):
        sequences = read_fasta(inputs[assembler])
        if not sequences:
            raise ValueError(f"assembler FASTA is empty: {assembler}")
        for original_id, sequence in sequences.items():
            if not sequence or set(sequence) - set("ACGTN"):
                raise ValueError(f"invalid DNA sequence from {assembler}: {original_id}")
            normalized = canonical_sequence(sequence)
            sequence_sources[normalized].append({
                "assembler": assembler,
                "original_id": original_id,
                "orientation_normalized": sequence != normalized,
            })

    records = []
    fasta_lines: list[str] = []
    query_to_assemblers: dict[str, list[str]] = {}
    for sequence in sorted(sequence_sources, key=lambda item: (hashlib.sha256(item.encode()).hexdigest(), item)):
        sources = sequence_sources[sequence]
        assemblers = sorted({source["assembler"] for source in sources})
        digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
        query_id = f"gic_{digest[:20]}"
        query_to_assemblers[query_id] = assemblers
        fasta_lines.extend([f">{query_id}", sequence])
        records.append({
            "query_id": query_id,
            "sequence_sha256": digest,
            "length_bp": len(sequence),
            "supporting_assemblers": assemblers,
            "support_count": len(assemblers),
            "exact_sequence_concordance": (
                "MULTI_ASSEMBLER_EXACT" if len(assemblers) >= 2 else "SINGLE_ASSEMBLER_ONLY"
            ),
            "sources": sorted(sources, key=lambda item: (item["assembler"], item["original_id"])),
        })

    successful = sorted(
        assembler for assembler, status in statuses.items() if status in {"SUCCESS", "SOFT"}
    )
    manifest = {
        "schema_version": "1.0",
        "analysis_profile": profile_id,
        "strategy": "assembly-consensus",
        "evidence_authority": "ANALYSIS",
        "concordance_kind": "EXACT_SEQUENCE_AND_REFERENCE_LOCUS",
        "minimum_successful_assemblers": minimum_successful,
        "successful_assemblers": successful,
        "consensus_requirement_met": len(successful) >= minimum_successful,
        "assembler_status": {key: statuses[key] for key in sorted(statuses)},
        "sequence_count": len(records),
        "multi_assembler_exact_sequence_count": sum(
            record["support_count"] >= 2 for record in records
        ),
        "query_to_assemblers": query_to_assemblers,
        "sequences": records,
        "scientific_caveat": (
            "Assembler concordance is a robustness observation and never promotes "
            "a candidate or evidence level by itself."
        ),
    }
    write_text_atomic(out_fasta, "\n".join(fasta_lines) + ("\n" if fasta_lines else ""))
    write_json_atomic(out_manifest, manifest)
    return manifest


def locus_concordance(loci_path: Path, manifest_path: Path, out_tsv: Path, out_json: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="strict"))
    if manifest.get("schema_version") != "1.0" or manifest.get("strategy") != "assembly-consensus":
        raise ValueError("invalid assembly consensus manifest")
    mapping = manifest.get("query_to_assemblers")
    if not isinstance(mapping, dict):
        raise ValueError("assembly consensus manifest has no query mapping")
    rows = []
    by_key = {}
    for locus in read_tsv(loci_path):
        query_ids = [item for item in locus.get("query_ids", "").split(";") if item]
        assemblers = sorted({
            assembler
            for query_id in query_ids
            for assembler in mapping.get(query_id, [])
        })
        key = "|".join([
            locus.get("sseqid", ""),
            locus.get("category", ""),
            locus.get("locus_id", ""),
        ])
        status = (
            "MULTI_ASSEMBLER_LOCUS" if len(assemblers) >= 2
            else "SINGLE_ASSEMBLER_LOCUS" if assemblers
            else "NOT_EVALUATED"
        )
        row = {
            "reference_id": locus.get("sseqid", ""),
            "category": locus.get("category", ""),
            "locus_id": locus.get("locus_id", ""),
            "query_ids": ";".join(query_ids),
            "supporting_assemblers": ";".join(assemblers),
            "support_count": len(assemblers),
            "concordance_status": status,
        }
        rows.append(row)
        by_key[key] = {
            "supporting_assemblers": assemblers,
            "support_count": len(assemblers),
            "status": status,
        }
    write_tsv_atomic(
        out_tsv,
        rows,
        [
            "reference_id", "category", "locus_id", "query_ids",
            "supporting_assemblers", "support_count", "concordance_status",
        ],
    )
    result = {
        "schema_version": "1.0",
        "analysis_profile": manifest.get("analysis_profile"),
        "evidence_authority": "ANALYSIS",
        "locus_count": len(rows),
        "multi_assembler_locus_count": sum(
            row["concordance_status"] == "MULTI_ASSEMBLER_LOCUS" for row in rows
        ),
        "by_locus": by_key,
    }
    write_json_atomic(out_json, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and inspect multi-assembler concordance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    combine_parser = subparsers.add_parser("combine")
    combine_parser.add_argument("--input", action="append", default=[], help="ASSEMBLER=FASTA")
    combine_parser.add_argument("--status", action="append", default=[], help="ASSEMBLER=STATUS")
    combine_parser.add_argument("--out-fasta", required=True, type=Path)
    combine_parser.add_argument("--out-manifest", required=True, type=Path)
    combine_parser.add_argument("--minimum-successful", required=True, type=int)
    combine_parser.add_argument("--profile", required=True)

    locus_parser = subparsers.add_parser("loci")
    locus_parser.add_argument("--loci", required=True, type=Path)
    locus_parser.add_argument("--manifest", required=True, type=Path)
    locus_parser.add_argument("--out-tsv", required=True, type=Path)
    locus_parser.add_argument("--out-json", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "combine":
        inputs = {
            key: Path(value)
            for key, value in parse_key_values(args.input, ASSEMBLERS, "assembler input").items()
        }
        statuses = parse_key_values(args.status, ASSEMBLERS, "assembler status")
        combine(
            inputs, statuses, args.out_fasta, args.out_manifest,
            args.minimum_successful, args.profile,
        )
    else:
        locus_concordance(args.loci, args.manifest, args.out_tsv, args.out_json)


if __name__ == "__main__":
    main()
