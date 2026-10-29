#!/usr/bin/env python3
"""Export every aligned query for human review, independently of its tier."""
from __future__ import annotations

import argparse
from collections.abc import Iterable
import gzip
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import read_fasta, iter_tsv, sha256_text, write_json_atomic, write_text_atomic, write_tsv_atomic

_TITLE_CUT = re.compile(
    r",|\s+strain\b|\s+isolate\b|\s+complete\b|\s+genomic\b|\s+genome\b|\s+partial\b",
    re.IGNORECASE,
)
_ACCESSION = re.compile(r"^[A-Za-z0-9_.|:.-]+$")
# The Builder already publishes sequences from 20 bp and keeps the 200 bp
# boundary for its contig FASTA. This mark records that boundary; it does not
# move it.
_BUILDER_SHORT_BP = 200


def export(queries: Path, manifest_path: Path, fragments: Path, output: Path,
           reference_fasta: Path | None = None, blast_db: Path | None = None):
    sequences = read_fasta(queries) if queries.stat().st_size else {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reference_lengths = {}
    subjects = set()
    for row in iter_tsv(fragments):
        query = row["qseqid"]
        reference_lengths[query] = max(reference_lengths.get(query, 0), int(row.get("slen") or 0))
        if row.get("sseqid"):
            subjects.add(str(row["sseqid"]))
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
    grouped = {}

    def rows():
        for row in iter_tsv(fragments):
            candidate = {"qseqid": row["qseqid"], "sequence_length_bp": len(sequences[row["qseqid"]]),
                         "sequence_sha256": metadata[row["qseqid"]]["sequence_sha256"],
                         "query_origins": ";".join(sorted(metadata[row["qseqid"]]["source_counts"])),
                         "aligned_query_bp": row["query_covered_bp"],
                         **{key: row.get(key, "") for key in fields if key in row and key != "qseqid"}}
            _accumulate_summary(grouped, candidate)
            yield candidate

    write_tsv_atomic(output / "candidate_sequences.tsv", rows(), fields)
    catalog = load_reference_catalog(reference_fasta, blast_db, sorted(subjects))
    summary_fields = fields + [
        "reference_description", "min_evalue", "hit_row_count",
        "fragmento_curto", "rotulo",
    ]
    write_tsv_atomic(output / "candidate_summary.tsv", _summary_rows(grouped, catalog), summary_fields)
    write_json_atomic(output / "candidate_queries.json", manifest)


def _rank_number(row: dict, key: str, default: float) -> float:
    try:
        return float(row.get(key) or "")
    except (TypeError, ValueError):
        return default


def _best_rank(row: dict) -> tuple:
    """Same order already used for hits: higher bitscore, then lower e-value, then higher identity."""
    return (
        -_rank_number(row, "best_bitscore", float("-inf")),
        _rank_number(row, "best_evalue", float("inf")),
        -_rank_number(row, "weighted_pident", float("-inf")),
        str(row.get("sseqid", "")),
        str(row.get("task", "")),
    )


def _identifier_keys(identifier: str) -> list[str]:
    keys = [identifier] if identifier else []
    if "|" in identifier:
        keys.extend(part for part in identifier.split("|") if part and part not in keys)
    return keys


def organism_from_title(title: str, accession: str = "") -> str:
    """Organism phrase from a reference title. Empty when the title is only an accession."""
    text = title.strip()
    if accession and text.startswith(accession):
        text = text[len(accession):].strip()
    bracket = re.search(r"\[([^\[\]]+)\]\s*$", text)
    if bracket:
        return bracket.group(1).strip()
    cut = _TITLE_CUT.split(text, maxsplit=1)[0].strip(" ,;")
    if not cut or _ACCESSION.fullmatch(cut):
        return ""
    return cut


def _remember(catalog: dict[str, tuple[str, str]], identifier: str, description: str) -> None:
    description = description.strip()
    if not identifier or not description:
        return
    record = (description, organism_from_title(description, identifier))
    for key in _identifier_keys(identifier):
        catalog.setdefault(key, record)


def titles_from_fasta(path: Path) -> dict[str, tuple[str, str]]:
    """Stream FASTA titles. A bad encoding or gzip never aborts the export."""
    try:
        return _titles_from_fasta_stream(path)
    except Exception as exc:
        print(
            f"[AVISO] Não foi possível ler títulos de {path}: {exc}. "
            "Descrições de referência ficam vazias.",
            file=sys.stderr,
        )
        return {}


def _titles_from_fasta_stream(path: Path) -> dict[str, tuple[str, str]]:
    catalog: dict[str, tuple[str, str]] = {}
    if path.name.endswith(".gz"):
        handle = gzip.open(path, "rt", encoding="utf-8", errors="replace")
    else:
        handle = path.open("r", encoding="utf-8", errors="replace")
    with handle:
        for raw in handle:
            if not raw.startswith(">"):
                continue
            header = raw[1:].strip()
            identifier, _, title = header.partition(" ")
            _remember(catalog, identifier, title or header)
    return catalog


def _catalog_from_blastdbcmd(stdout: str) -> dict[str, tuple[str, str]]:
    catalog: dict[str, tuple[str, str]] = {}
    for line in stdout.splitlines():
        accession, separator, title = line.partition("\t")
        accession = accession.strip()
        title = title.strip()
        if not separator or not accession or not title:
            continue
        _remember(catalog, accession, title)
        # Without -parse_seqids, %a is BL_ORD_ID:N and blastn sseqid is the
        # first token of the original FASTA header, which %t still carries.
        if accession.startswith("BL_ORD_ID"):
            token = title.split(None, 1)[0]
            if token and token != accession:
                _remember(catalog, token, title)
    return catalog


def _blastdbcmd(prefix: Path, entry_args: list[str]) -> dict[str, tuple[str, str]] | None:
    try:
        result = subprocess.run(
            ["blastdbcmd", "-db", str(prefix), *entry_args, "-outfmt", "%a\t%t"],
            capture_output=True, text=True, check=False, timeout=120,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if result.returncode != 0 or result.stdout is None:
        return None
    return _catalog_from_blastdbcmd(result.stdout)


def _blast_db_has_seqid_index(prefix: Path) -> bool:
    """True when makeblastdb -parse_seqids built an accession index.

    BLAST 2.12 writes ``.nog`` for that index. Older releases used ``.nsi``
    and ``.nsd``. Without it, ``-entry_batch`` cannot resolve a FASTA id.
    """
    return any(Path(f"{prefix}{suffix}").is_file() for suffix in (".nog", ".nsi", ".nsd"))


def titles_from_blast_db(prefix: Path, subjects: list[str] | None = None) -> dict[str, tuple[str, str]]:
    """Read accession and title. ``%f`` is FASTA and ignores every other specifier.

    Hit accessions use ``-entry_batch`` only when the database has an id
    index. Without ``-parse_seqids`` that call cannot resolve the FASTA id,
    so the reader goes straight to ``-entry all``. A missing subject also
    falls back to ``-entry all``.
    """
    if shutil.which("blastdbcmd") is None:
        return {}
    wanted = [subject for subject in (subjects or []) if subject]
    if wanted and _blast_db_has_seqid_index(prefix):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as handle:
            handle.write("\n".join(wanted) + "\n")
            handle.flush()
            batched = _blastdbcmd(prefix, ["-entry_batch", handle.name])
        if batched is not None and all(_catalog_record(batched, subject)[0] for subject in wanted):
            return batched
    return _blastdbcmd(prefix, ["-entry", "all"]) or {}


def load_reference_catalog(
    reference_fasta: Path | None,
    blast_db: Path | None,
    subjects: list[str] | None = None,
) -> dict[str, tuple[str, str]]:
    catalog: dict[str, tuple[str, str]] = {}
    if reference_fasta is not None and reference_fasta.is_file():
        catalog.update(titles_from_fasta(reference_fasta))
    if blast_db is not None:
        for key, record in titles_from_blast_db(blast_db, subjects).items():
            catalog.setdefault(key, record)
    return catalog


def _catalog_record(catalog: dict[str, tuple[str, str]], subject: str) -> tuple[str, str]:
    if subject in catalog:
        return catalog[subject]
    for key in _identifier_keys(subject):
        if key in catalog:
            return catalog[key]
    return "", ""


def _accumulate_summary(grouped: dict, row: dict) -> None:
    query = row["qseqid"]
    rank = _best_rank(row)
    number = _rank_number(row, "best_evalue", float("inf"))
    state = grouped.get(query)
    if state is None:
        state = {"best": row, "rank": rank, "count": 0,
                 "min_number": None, "min_text": ""}
        grouped[query] = state
    elif rank < state["rank"]:
        state["best"], state["rank"] = row, rank
    state["count"] += 1
    if math.isfinite(number) and (state["min_number"] is None or number < state["min_number"]):
        state["min_number"] = number
        state["min_text"] = str(row.get("best_evalue", ""))


def _builder_short(row: dict) -> bool:
    method = str(row.get("assembly_method") or "").lower()
    if "builder" not in {part.strip() for part in method.split(",")}:
        return False
    try:
        length = int(row.get("sequence_length_bp") or 0)
    except (TypeError, ValueError):
        return False
    return length < _BUILDER_SHORT_BP


def _summary_rows(grouped: dict, catalog: dict[str, tuple[str, str]]):
    for state in grouped.values():
        best = dict(state["best"])
        description, hinted_taxon = _catalog_record(catalog, str(best.get("sseqid", "")))
        if not str(best.get("taxon") or "") and hinted_taxon:
            best["taxon"] = hinted_taxon
        short = _builder_short(best)
        # A Builder record below 200 bp stays at REVIEW. Other rows remain candidates.
        yield {**best, "reference_description": description,
               "min_evalue": state["min_text"], "hit_row_count": str(state["count"]),
               "fragmento_curto": "true" if short else "false",
               "rotulo": "REVIEW" if short else "CANDIDATO"}


def _best_hit_rows(rows: Iterable[dict], catalog: dict[str, tuple[str, str]] | None = None) -> list[dict]:
    """Same best hit, ties and first-query order; memory scales with candidates."""
    grouped = {}
    for row in rows:
        _accumulate_summary(grouped, row)
    return list(_summary_rows(grouped, catalog or {}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fragments", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--reference-fasta", type=Path)
    parser.add_argument("--blast-db", type=Path)
    args = parser.parse_args()
    export(args.queries, args.manifest, args.fragments, args.out_dir, args.reference_fasta, args.blast_db)


if __name__ == "__main__":
    main()
