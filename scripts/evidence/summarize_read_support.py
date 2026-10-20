#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from collections import defaultdict

try:
    from .common import parse_intervals, read_tsv, write_tsv_atomic
except ImportError:
    from common import parse_intervals, read_tsv, write_tsv_atomic


FIELDS = [
    "sample_id", "reference_id", "category", "locus_id", "orientation", "query_ids",
    "library_mode", "umi_mode", "support_status", "unique_templates", "distinct_starts",
    "proper_pair_templates", "discordant_templates", "minimum_mapq",
]
CIGAR_RE = re.compile(r"(\d+)([MIDNSHP=X])")


def cigar_reference_span(cigar: str) -> int:
    operations = [(int(size), op) for size, op in CIGAR_RE.findall(cigar)]
    if not operations or "".join(f"{size}{op}" for size, op in operations) != cigar:
        raise ValueError(f"invalid CIGAR: {cigar}")
    return sum(size for size, op in operations if op in {"M", "D", "N", "=", "X"})


def five_prime(position: int, cigar: str, reverse: bool) -> int:
    operations = [(int(size), op) for size, op in CIGAR_RE.findall(cigar)]
    if not reverse:
        leading_clip = operations[0][0] if operations[0][1] in {"S", "H"} else 0
        return position - leading_clip
    trailing_clip = operations[-1][0] if operations[-1][1] in {"S", "H"} else 0
    return position + cigar_reference_span(cigar) + trailing_clip - 1


def load_loci(path: str | None) -> list[dict[str, str]]:
    if not path:
        return []
    rows = read_tsv(path)
    required = {"locus_id", "sseqid", "category", "orientation", "query_ids", "reference_intervals"}
    if rows and not required.issubset(rows[0]):
        raise ValueError(f"locus table missing columns: {', '.join(sorted(required - set(rows[0])))}")
    return rows


def _overlaps_locus(reference: str, start: int, end: int, locus: dict[str, str]) -> bool:
    if locus["sseqid"] != reference:
        return False
    return any(max(start, left) <= min(end, right) for left, right in parse_intervals(locus["reference_intervals"]))


def summarize_sam(path: str, sample: str, library_mode: str, umi_mode: str,
                  minimum_mapq: int, loci: list[dict[str, str]] | None = None) -> list[dict]:
    loci = loci or []
    templates_by_key: dict[tuple[str, str, str, str, str], dict[str, dict]] = defaultdict(dict)
    # A completed SAM scan measures zero for a supplied locus with no accepted
    # alignment. Missing remapping inputs never invoke this summarizer.
    for locus in loci:
        key = (locus["sseqid"], locus["category"], locus["locus_id"],
               locus.get("orientation", ""), locus.get("query_ids", ""))
        templates_by_key[key] = {}
    with open(path, "r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.startswith("@"):
                continue
            cols = raw.rstrip("\r\n").split("\t")
            if len(cols) < 11:
                raise ValueError(f"{path}:{line_number}: malformed SAM row has fewer than 11 columns")
            qname, flag_text, reference, position_text, mapq_text, cigar = cols[:6]
            try:
                flag, position, mapq = int(flag_text), int(position_text), int(mapq_text)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid SAM numeric field") from exc
            if flag & 0x4 or flag & 0x100 or flag & 0x800 or mapq < minimum_mapq:
                continue
            if reference == "*" or cigar == "*":
                raise ValueError(f"{path}:{line_number}: mapped SAM row lacks reference or CIGAR")
            try:
                span = cigar_reference_span(cigar)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            end = position + span - 1
            matched_loci = [locus for locus in loci if _overlaps_locus(reference, position, end, locus)]
            if not loci:
                matched_loci = [{
                    "sseqid": reference, "category": "UNLABELED",
                    "locus_id": f"REFERENCE::{reference}", "orientation": "",
                    "query_ids": "",
                }]
            reverse = bool(flag & 0x10)
            start = five_prime(position, cigar, reverse)
            for locus in matched_loci:
                key = (locus["sseqid"], locus["category"], locus["locus_id"],
                       locus.get("orientation", ""), locus.get("query_ids", ""))
                record = templates_by_key[key].setdefault(
                    qname, {"starts": [], "proper": False, "discordant": False}
                )
                record["starts"].append((reference, start, "-" if reverse else "+"))
                record["proper"] = record["proper"] or bool(flag & 0x2)
                record["discordant"] = record["discordant"] or (bool(flag & 0x1) and not bool(flag & 0x2))

    rows = []
    for key, templates in sorted(templates_by_key.items()):
        template_keys: set[tuple] = set()
        starts: set[tuple] = set()
        proper = discordant = 0
        for record in templates.values():
            ordered = tuple(sorted(record["starts"]))
            template_keys.add(ordered)
            starts.update(record["starts"])
            proper += bool(record["proper"])
            discordant += bool(record["discordant"])
        reference, category, locus_id, orientation, query_ids = key
        rows.append({
            "sample_id": sample, "reference_id": reference, "category": category,
            "locus_id": locus_id, "orientation": orientation, "query_ids": query_ids,
            "library_mode": library_mode, "umi_mode": umi_mode,
            "support_status": "SUPPORT_AVAILABLE", "unique_templates": len(template_keys),
            "distinct_starts": len(starts), "proper_pair_templates": proper,
            "discordant_templates": discordant, "minimum_mapq": minimum_mapq,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize candidate-scoped template support from primary SAM alignments")
    parser.add_argument("--sam", required=True)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--loci")
    parser.add_argument("--library-mode", required=True, choices=["shotgun", "amplicon", "targeted", "unknown"])
    parser.add_argument("--umi-mode", default="none", choices=["none", "read_name", "tag"])
    parser.add_argument("--minimum-mapq", type=int, default=10)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    write_tsv_atomic(
        args.out,
        summarize_sam(args.sam, args.sample, args.library_mode, args.umi_mode,
                      args.minimum_mapq, load_loci(args.loci)),
        FIELDS,
    )


if __name__ == "__main__":
    main()
