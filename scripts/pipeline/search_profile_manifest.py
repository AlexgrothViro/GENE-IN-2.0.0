#!/usr/bin/env python3
"""Freeze which search profile (GEN-013 A/B/C) a run actually performed.

``resolve_config.py`` decides the profile identity once, from the flags the
run was given; this module turns that decision into a durable artifact next
to the BLAST results, so the identity survives the run even when Evidence is
off and nothing else records it.

The manifest is a declaration, never a switch: it reports the profiles that
were selected and the artifacts they produced. It never enables a profile,
and it never fails a run — an artifact that a profile did not produce is
recorded as absent rather than treated as an error.

Profile labels are the contract labels A/B/C plus the pre-existing flags
each one maps to. The literal product IDs are still open (GEN-013), so no
name is invented here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"


def _artifact(path: str) -> dict:
    """Describe one artifact path without ever failing on a missing file."""
    entry: dict = {"path": path, "present": False, "size": 0}
    if not path:
        return entry
    candidate = Path(path)
    try:
        if candidate.is_file():
            entry["present"] = True
            entry["size"] = candidate.stat().st_size
    except OSError:
        pass
    return entry


def _database_identity(config: dict, database_manifest: str) -> dict:
    """Database identity for the directed DB shared by profiles A and C."""
    identity = {
        "blast_db": config.get("blast_db", ""),
        "db": config.get("db", ""),
        "db_query": config.get("db_query", ""),
        "manifest": _artifact(database_manifest),
        "generation_id": "",
        "source_fasta_sha256": "",
    }
    if identity["manifest"]["present"]:
        try:
            with open(database_manifest, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, ValueError):
            return identity
        identity["generation_id"] = str(manifest.get("generation_id", ""))
        source = manifest.get("source_fasta")
        if isinstance(source, dict):
            identity["source_fasta_sha256"] = str(source.get("sha256", ""))
    return identity


def _omitted_scoring(task: str) -> dict[str, int]:
    evidence = Path(__file__).resolve().parents[1] / "evidence"
    if str(evidence) not in sys.path:
        sys.path.insert(0, str(evidence))
    from blast_router import omitted_scoring

    return omitted_scoring(task)


def effective_blast_record(
    config: dict,
    *,
    max_target_seqs: str = "",
    database_sequence_count: str = "",
) -> dict[str, str]:
    """Values already chosen for this run, in the names provenance records.

    Word size and e-value come from the resolved configuration (the same
    fields profile A stores). Reward, penalty and gaps are what blastn
    applies for that task when the contig search omits those flags.
    """
    task = str(config.get("blast_task") or "blastn")
    scoring = _omitted_scoring(task)
    return {
        "blast_evalue": str(config.get("blast_evalue", "")),
        "blastn_word_size": str(config.get("blast_word_size", "")),
        "blast_gapopen": str(scoring["gapopen"]),
        "blast_gapextend": str(scoring["gapextend"]),
        "blastn_reward": str(scoring["reward"]),
        "blastn_penalty": str(scoring["penalty"]),
        "blast_max_target_seqs": str(max_target_seqs),
        "blast_database_sequence_count": str(database_sequence_count),
    }


def build_manifest(
    *,
    config: dict,
    sample: str,
    database_manifest: str = "",
    contigs: str = "",
    contig_blast_tsv: str = "",
    short_fragment_fasta: str = "",
    short_fragment_blast_tsv: str = "",
    short_fragment_filtered_tsv: str = "",
    max_target_seqs: str = "",
    database_sequence_count: str = "",
) -> dict:
    profile = config.get("search_profile", {})
    short_fragment = config.get("short_fragment", {})
    evidence = config.get("evidence", {})
    database = _database_identity(config, database_manifest)

    return {
        "schema_version": SCHEMA_VERSION,
        "sample": sample,
        "effective_blast": effective_blast_record(
            config,
            max_target_seqs=max_target_seqs,
            database_sequence_count=database_sequence_count,
        ),
        "identity": profile.get("identity", ""),
        "requested": profile.get("requested", ""),
        "selected": profile.get("selected", ""),
        "evidence_v2": bool(evidence.get("v2", False)),
        "profiles": {
            "A": {
                "active": bool(profile.get("a_active", True)),
                "flags": profile.get("a_flags", ""),
                "search": {
                    "task": config.get("blast_task", ""),
                    "word_size": config.get("blast_word_size", ""),
                    "evalue": config.get("blast_evalue", ""),
                },
                "database": database,
                "artifacts": {
                    "query_fasta": _artifact(contigs),
                    "blast_tsv": _artifact(contig_blast_tsv),
                },
            },
            "B": {
                "active": bool(profile.get("b_active", False)),
                "flags": profile.get("b_flags", ""),
                "database": {
                    "composite_db": evidence.get("composite_db", ""),
                    "subject_labels": _artifact(evidence.get("subject_labels", "")),
                    "panel_fasta": _artifact(evidence.get("panel_fasta", "")),
                },
                "artifacts": {
                    "query_fasta": _artifact(contigs),
                },
            },
            "C": {
                "active": bool(profile.get("c_active", False)),
                "flags": profile.get("c_flags", ""),
                "search": {
                    "task": "blastn-short",
                    "word_size": short_fragment.get("word_size", ""),
                    "evalue": short_fragment.get("evalue", ""),
                    "min_len": short_fragment.get("min_len", ""),
                    "max_len": short_fragment.get("max_len", ""),
                    "min_pid": short_fragment.get("min_pid", ""),
                    "min_qcov": short_fragment.get("min_qcov", ""),
                },
                "database": database,
                "artifacts": {
                    "query_fasta": _artifact(short_fragment_fasta),
                    "blast_tsv": _artifact(short_fragment_blast_tsv),
                    "filtered_tsv": _artifact(short_fragment_filtered_tsv),
                },
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="resolved_config.json do run")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--database-manifest", default="")
    parser.add_argument("--contigs", default="")
    parser.add_argument("--contig-blast-tsv", default="")
    parser.add_argument("--short-fragment-fasta", default="")
    parser.add_argument("--short-fragment-blast-tsv", default="")
    parser.add_argument("--short-fragment-filtered-tsv", default="")
    parser.add_argument("--max-target-seqs", default="")
    parser.add_argument("--database-sequence-count", default="")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    manifest = build_manifest(
        config=config,
        sample=args.sample,
        database_manifest=args.database_manifest,
        contigs=args.contigs,
        contig_blast_tsv=args.contig_blast_tsv,
        short_fragment_fasta=args.short_fragment_fasta,
        short_fragment_blast_tsv=args.short_fragment_blast_tsv,
        short_fragment_filtered_tsv=args.short_fragment_filtered_tsv,
        max_target_seqs=args.max_target_seqs,
        database_sequence_count=args.database_sequence_count,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.name}.tmp")
    tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(out)


if __name__ == "__main__":
    main()
