#!/usr/bin/env python3
from __future__ import annotations

import argparse

try:
    from .activation_policy import load_public_activation_policy
    from .common import read_fasta, read_tsv, sequence_metrics, write_json_atomic
except ImportError:
    from activation_policy import load_public_activation_policy
    from common import read_fasta, read_tsv, sequence_metrics, write_json_atomic


def informative_sites(sequences: list[str]) -> int:
    if not sequences:
        return 0
    width = max(map(len, sequences))
    result = 0
    for index in range(width):
        counts: dict[str, int] = {}
        for sequence in sequences:
            state = sequence[index].upper() if index < len(sequence) else "-"
            if state in "ACGT":
                counts[state] = counts.get(state, 0) + 1
        if sum(count >= 2 for count in counts.values()) >= 2:
            result += 1
    return result


def candidate_scoped_information(query: str, references: list[str]) -> dict[str, int]:
    """Count information only where this candidate has an observed nucleotide.

    A column contributes only when the candidate state is represented in the
    reference panel and an alternative reference state is independently
    represented. Reference-only columns outside the candidate span cannot
    inflate the gate.
    """
    covered = informative = 0
    for index, raw_state in enumerate(query):
        state = raw_state.upper()
        if state not in "ACGT":
            continue
        covered += 1
        counts: dict[str, int] = {}
        for reference in references:
            ref_state = reference[index].upper() if index < len(reference) else "-"
            if ref_state in "ACGT":
                counts[ref_state] = counts.get(ref_state, 0) + 1
        alternatives = [count for base, count in counts.items() if base != state]
        if counts.get(state, 0) >= 1 and any(count >= 2 for count in alternatives):
            informative += 1
    return {
        "candidate_covered_columns": covered,
        "informative_sites_within_candidate_span": informative,
    }


def evaluate(alignment_path: str, query_path: str, reference_path: str, config: dict,
             metadata_path: str | None = None, competitive_path: str | None = None,
             iqtree_available: bool = True) -> dict:
    alignment = read_fasta(alignment_path)
    queries = read_fasta(query_path)
    references = read_fasta(reference_path)
    phy = config["phylogeny"]
    flags: list[str] = []
    missing_queries = sorted(set(queries) - set(alignment))
    missing_references = sorted(set(references) - set(alignment))
    if missing_queries:
        flags.append("QUERY_MISSING_FROM_ALIGNMENT")
    if missing_references:
        flags.append("REFERENCE_MISSING_FROM_ALIGNMENT")
    aligned_queries = {name: alignment[name] for name in queries if name in alignment}
    aligned_references = [alignment[name] for name in references if name in alignment]
    per_query = {
        name: candidate_scoped_information(sequence, aligned_references)
        for name, sequence in aligned_queries.items()
    }
    aligned_bp = min((item["candidate_covered_columns"] for item in per_query.values()), default=0)
    characters = sum(len(seq) for seq in aligned_queries.values())
    n_fraction = sum(seq.upper().count("N") for seq in aligned_queries.values()) / characters if characters else 1.0
    gap_fraction = sum(seq.count("-") for seq in aligned_queries.values()) / characters if characters else 1.0
    low_complexity = any(sequence_metrics(seq.replace("-", ""))["entropy"] < 1.2 for seq in aligned_queries.values())
    informative = min((item["informative_sites_within_candidate_span"] for item in per_query.values()), default=0)
    if aligned_bp < int(phy["minimum_aligned_bp"]): flags.append("INSUFFICIENT_ALIGNED_BP")
    if informative < int(phy["minimum_informative_sites"]): flags.append("INSUFFICIENT_INFORMATIVE_SITES")
    if len(references) < int(phy["minimum_references"]): flags.append("INSUFFICIENT_REFERENCES")
    if n_fraction > float(phy["maximum_n_fraction"]): flags.append("EXCESSIVE_N_FRACTION")
    if gap_fraction > float(phy["maximum_gap_fraction"]): flags.append("EXCESSIVE_GAP_FRACTION")
    if low_complexity: flags.append("LOW_COMPLEXITY")
    if not iqtree_available: flags.append("IQTREE_UNAVAILABLE")

    taxon_groups: set[str] = set()
    outgroup_present = False
    metadata_ids: set[str] = set()
    if metadata_path:
        rows = read_tsv(metadata_path)
        required = {"sseqid", "taxon_group", "is_outgroup"}
        if rows and not required.issubset(rows[0]):
            flags.append("INVALID_REFERENCE_METADATA")
        for row in rows:
            metadata_ids.add(row.get("sseqid", ""))
            if row.get("taxon_group"):
                taxon_groups.add(row["taxon_group"])
            outgroup_present = outgroup_present or row.get("is_outgroup", "").strip().lower() in {"1", "true", "yes"}
        if not set(references).issubset(metadata_ids) or len(taxon_groups) < 2 or not outgroup_present:
            flags.append("UNBALANCED_REFERENCE_PANEL")
    else:
        flags.append("REFERENCE_PANEL_METADATA_MISSING")

    chimera = False
    if competitive_path:
        taxa_by_query: dict[str, set[str]] = {}
        for row in read_tsv(competitive_path):
            if row.get("specificity_status") in {"AMBIGUOUS", "NON_TARGET_BEST"}:
                chimera = True
            taxon = row.get("target_taxon", "")
            if taxon:
                taxa_by_query.setdefault(row["qseqid"], set()).add(taxon)
        chimera = chimera or any(len(taxa) > 1 for taxa in taxa_by_query.values())
    if chimera:
        flags.append("CHIMERA_SUSPECTED")

    flags = list(dict.fromkeys(flags))
    return {
        "gate_status": "PASS" if not flags else "BLOCKED",
        "flags": flags,
        "metrics": {
            "aligned_bp": aligned_bp,
            "candidate_covered_columns": aligned_bp,
            "informative_sites": informative,
            "informative_sites_within_candidate_span": informative,
            "per_query": per_query,
            "reference_count": len(references),
            "n_fraction": n_fraction,
            "gap_fraction": gap_fraction,
            "taxon_groups": len(taxon_groups),
            "outgroup_present": outgroup_present,
        },
        "note": "Limiares operacionais provisórios até a conclusão do benchmark.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply operational phylogeny gates")
    parser.add_argument("--alignment", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--references", required=True)
    parser.add_argument("--activation-policy")
    parser.add_argument("--profiles")
    parser.add_argument("--reference-metadata")
    parser.add_argument("--competitive")
    parser.add_argument("--iqtree-available", choices=["true", "false"], default="true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    policy = load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)
    result = evaluate(args.alignment, args.queries, args.references, policy["thresholds"],
                      args.reference_metadata, args.competitive, args.iqtree_available == "true")
    write_json_atomic(args.out, result)
    raise SystemExit(0 if result["gate_status"] == "PASS" else 3)


if __name__ == "__main__":
    main()
