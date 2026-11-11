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
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from input_validation import iter_fasta, iter_fastq, _pair_id
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evidence"))
from common import sha256_file, write_json_atomic, write_text_atomic
from query_accounting import render_collection_summary


def collect(contigs: Path, short_fasta: Path | None = None,
            fastqs: list[Path] | None = None, rescue_fasta: Path | None = None,
            rescue_candidates: Path | None = None, restricted_fasta: Path | None = None):
    sequences = {}
    sequence_to_id = {}
    metadata = {}
    inputs = []

    accepted = {"short_20_100": 0, "long_above_100": 0, "legacy_fasta_below_20": 0}
    discarded = {"fastq_below_20_legacy_exclusion": 0, "rescue_not_selected": 0}
    restricted_count = 0

    def add(name, sequence, kind, preserve_id=False, source_path=None, mate=None,
            restriction=None):
        nonlocal restricted_count
        sequence = sequence.upper()
        if not sequence or set(sequence) - set("ACGTRYSWKMBDHVN"):
            raise ValueError(f"Invalid nucleotide query: {name}")
        route = ("legacy_fasta_below_20" if len(sequence) < 20 else
                 "short_20_100" if len(sequence) <= 100 else "long_above_100")
        accepted[route] += 1
        restricted_count += bool(restriction)
        digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
        query_id = name if preserve_id else sequence_to_id.get(sequence, f"gir_{digest}")
        if query_id in sequences and sequences[query_id] != sequence:
            raise ValueError(f"Query ID collision: {query_id}")
        sequences[query_id] = sequence
        sequence_to_id.setdefault(sequence, query_id)
        entry = metadata.setdefault(query_id, {"length_bp": len(sequence),
            "sequence_sha256": digest, "source_counts": {}})
        entry["source_counts"][kind] = entry["source_counts"].get(kind, 0) + 1
        origin = {"id": name, "path": str(source_path.resolve()) if source_path else None,
                  "kind": kind}
        if kind in {"short_read", "long_read", "rescue_read"}:
            origin.update(read_id=name, pair_id=_pair_id(name), mate=mate)
        if restriction:
            origin["restriction"] = restriction
            entry.setdefault("restrictions", [])
            if restriction not in entry["restrictions"]:
                entry["restrictions"].append(restriction)
        entry.setdefault("sources", []).append(origin)

    def fasta(path, kind, preserve_id=False, restriction=None):
        inputs.append({"path": str(path.resolve()), "kind": kind, "sha256": sha256_file(path)})
        if path.stat().st_size:
            for name, sequence in iter_fasta(path):
                add(name, sequence, kind, preserve_id, source_path=path, restriction=restriction)

    fasta(contigs, "contig", True)
    if short_fasta is not None:
        fasta(short_fasta, "assembled_short")
    if restricted_fasta is not None:
        fasta(restricted_fasta, "assembled_restricted", restriction="ESPECIFICIDADE_NAO_VALIDADA")
    for index, path in enumerate(fastqs or []):
        inputs.append({"path": str(path.resolve()), "kind": "short_read",
                       "sha256": sha256_file(path)})
        for name, sequence in iter_fastq(path):
            if len(sequence) < 20:
                discarded["fastq_below_20_legacy_exclusion"] += 1
                continue
            kind = "short_read" if len(sequence) <= 100 else "long_read"
            add(name, sequence, kind, source_path=path,
                mate=index + 1 if len(fastqs) == 2 else None)
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
                add(name, sequence, "rescue_read", source_path=rescue_fasta)
                found.add(name)
            else:
                discarded["rescue_not_selected"] += 1
        if found != hit_ids:
            raise ValueError("rescue selection contains query IDs absent from rescue FASTA")
    return sequences, {"schema_version": "1.0", "deduplication": "exact_same_orientation",
                       "count_unit": "source_occurrence_not_independent_template",
                       "inputs": inputs, "queries": metadata,
                       "routing_summary": {
                           "accepted_occurrences": accepted,
                           "discarded_occurrences": discarded,
                           "unique_queries": len(sequences),
                           "merged_occurrences": sum(accepted.values()) - len(sequences),
                           "restricted_occurrences": restricted_count}}


def builder_inputs(manifest_path: Path) -> dict:
    """Explicit import of completed Builder 3.0.0b1 outputs, not its old CLI adapter.

    Read only fixed published paths under the manifest directory. Do not execute
    commands or follow paths provided by the manifest.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("genein_builder") != "3.0.0b1" or
            manifest.get("estado") != "concluido" or manifest.get("status") != "ok"):
        raise ValueError("Requer manifesto concluído e ok do Builder 3.0.0b1")
    root = manifest_path.resolve().parent
    def published(relative):
        path = root / relative
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Saída Builder ausente ou fora da pasta: {relative}")
        return path
    return {"contigs": published("contigs.fasta"),
            "short_fasta": published("fragmentos/fragmentos.fasta"),
            "restricted_fasta": published("fragmentos/fragmentos_restritos.fasta"),
            "fastqs": [published(f"nao_montadas_R{mate}.fq.gz") for mate in (1, 2)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contigs", type=Path)
    parser.add_argument("--builder-manifest", type=Path)
    parser.add_argument("--restricted-fasta", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--short-fasta", type=Path)
    parser.add_argument("--fastq", type=Path, action="append", default=[])
    parser.add_argument("--rescue-fasta", type=Path)
    parser.add_argument("--rescue-candidates", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--supplement-out", type=Path,
                        help="Only short queries and rescue queries; longer contigs retain their existing search")
    args = parser.parse_args()
    if args.builder_manifest:
        if any((args.contigs, args.short_fasta, args.fastq, args.restricted_fasta,
                args.rescue_fasta, args.rescue_candidates)):
            parser.error("--builder-manifest não pode ser combinado com entradas manuais")
        sequences, manifest = collect(**builder_inputs(args.builder_manifest))
        manifest["inputs"].append({"path": str(args.builder_manifest.resolve()),
                                   "kind": "builder_manifest",
                                   "sha256": sha256_file(args.builder_manifest)})
    else:
        if args.contigs is None:
            parser.error("informe --contigs ou --builder-manifest")
        sequences, manifest = collect(args.contigs, args.short_fasta, args.fastq,
                                      args.rescue_fasta, args.rescue_candidates,
                                      args.restricted_fasta)
    summary = render_collection_summary(manifest)
    print(summary)
    if args.summary:
        write_text_atomic(args.summary, summary)
    write_text_atomic(args.out, "".join(f">{name}\n{seq}\n" for name, seq in sequences.items()))
    write_json_atomic(args.manifest, manifest)
    if args.supplement_out:
        write_text_atomic(args.supplement_out, "".join(
            f">{name}\n{seq}\n" for name, seq in sequences.items()
            if len(seq) <= 100 or "contig" not in manifest["queries"][name]["source_counts"]))


if __name__ == "__main__":
    main()
