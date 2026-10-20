#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
from collections import defaultdict
from pathlib import Path

try:
    from .common import parse_intervals, read_tsv, sha256_text, write_tsv_atomic
except ImportError:
    from common import parse_intervals, read_tsv, sha256_text, write_tsv_atomic


FIELDS = [
    "lineage_record_id", "lineage_id", "sample_id", "reference_id", "locus_id",
    "orientation", "query_ids", "source_template_digests", "final_umi",
    "umi_group_method", "library_mode", "umi_mode", "template_count",
    "read_count", "mapped_bases", "proper_pair_templates", "discordant_templates",
    "eligible", "rejection_reason", "rule_id",
]
CIGAR_RE = re.compile(r"(\d+)([MIDNSHP=X])")
TAG_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]):([AifZHB]):(.+)$")


def cigar_mapped_bases_in_locus(
    position: int,
    cigar: str,
    locus_intervals: list[tuple[int, int]],
) -> int:
    """Count reference bases consumed by M/=/X that intersect locus intervals."""
    operations = [(int(size), op) for size, op in CIGAR_RE.findall(cigar)]
    if not operations or "".join(f"{size}{op}" for size, op in operations) != cigar:
        raise ValueError(f"invalid CIGAR: {cigar}")
    ref_pos = position
    mapped = 0
    for size, op in operations:
        if op in {"M", "=", "X"}:
            start = ref_pos
            end = ref_pos + size - 1
            for left, right in locus_intervals:
                overlap_start = max(start, left)
                overlap_end = min(end, right)
                if overlap_start <= overlap_end:
                    mapped += overlap_end - overlap_start + 1
            ref_pos += size
        elif op in {"D", "N"}:
            ref_pos += size
        elif op in {"I", "S", "H", "P"}:
            continue
        else:
            raise ValueError(f"unsupported CIGAR op: {op}")
    return mapped


def cigar_reference_span(cigar: str) -> int:
    operations = [(int(size), op) for size, op in CIGAR_RE.findall(cigar)]
    if not operations or "".join(f"{size}{op}" for size, op in operations) != cigar:
        raise ValueError(f"invalid CIGAR: {cigar}")
    return sum(size for size, op in operations if op in {"M", "D", "N", "=", "X"})


def _parse_tags(cols: list[str]) -> dict[str, str]:
    tags: dict[str, str] = {}
    for item in cols[11:]:
        match = TAG_RE.match(item)
        if not match:
            continue
        tags[match.group(1)] = match.group(3)
    return tags


def _overlaps_locus(reference: str, start: int, end: int, locus: dict[str, str]) -> bool:
    if locus["sseqid"] != reference:
        return False
    return any(
        max(start, left) <= min(end, right)
        for left, right in parse_intervals(locus["reference_intervals"])
    )


def _lineage_id(run_id: str, sample_id: str, final_umi: str, qname_digests: list[str]) -> str:
    parts = [run_id, sample_id, final_umi, *sorted(qname_digests)]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _lineage_record_id(payload: str) -> str:
    return "TLR_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _resolve_umi_by_qname(
    ug_by_qname: dict[str, set[str]],
    bx_by_qname: dict[str, set[str]],
) -> tuple[dict[str, str], dict[str, str]]:
    resolved_ug: dict[str, str] = {}
    resolved_bx: dict[str, str] = {}
    for qname, values in ug_by_qname.items():
        if len(values) > 1:
            raise ValueError(f"inconsistent UG tags for QNAME={qname}: {sorted(values)}")
        if values:
            resolved_ug[qname] = next(iter(values))
    for qname, values in bx_by_qname.items():
        if len(values) > 1:
            raise ValueError(f"inconsistent BX tags for QNAME={qname}: {sorted(values)}")
        if values:
            resolved_bx[qname] = next(iter(values))
    return resolved_ug, resolved_bx


def build_rows_from_sam(
    sam_path: str | Path,
    *,
    run_id: str,
    sample_id: str,
    library_mode: str,
    umi_mode: str,
    loci: list[dict[str, str]],
    require_umi_tags: bool,
) -> list[dict]:
    if not loci:
        return []

    # Pass 1: index primary alignments; collect UG/BX by QNAME when present.
    alignments: list[dict] = []
    ug_by_qname: dict[str, set[str]] = defaultdict(set)
    bx_by_qname: dict[str, set[str]] = defaultdict(set)

    with Path(sam_path).open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.startswith("@"):
                continue
            cols = raw.rstrip("\r\n").split("\t")
            if len(cols) < 11:
                raise ValueError(f"{sam_path}:{line_number}: malformed SAM row")
            qname, flag_text, reference, position_text, mapq_text, cigar = cols[:6]
            try:
                flag = int(flag_text)
                position = int(position_text)
                int(mapq_text)
            except ValueError as exc:
                raise ValueError(f"{sam_path}:{line_number}: invalid SAM numeric field") from exc
            if flag & 0x4 or flag & 0x100 or flag & 0x800:
                continue
            if reference == "*" or cigar == "*":
                raise ValueError(f"{sam_path}:{line_number}: mapped SAM row lacks reference or CIGAR")
            tags = _parse_tags(cols)
            ug = tags.get("UG")
            bx = tags.get("BX")
            if ug:
                ug_by_qname[qname].add(ug)
            if bx:
                bx_by_qname[qname].add(bx)
            alignments.append({
                "qname": qname,
                "flag": flag,
                "reference": reference,
                "position": position,
                "cigar": cigar,
                "line_number": line_number,
            })

    resolved_ug, resolved_bx = _resolve_umi_by_qname(ug_by_qname, bx_by_qname)

    # Pass 2: assign group_key from resolved UG for QNAMEs that have it.
    groups: dict[tuple[str, str], dict] = {}
    locus_qnames: set[str] = set()
    bx_by_group: dict[str, set[str]] = defaultdict(set)

    for alignment in alignments:
        qname = alignment["qname"]
        flag = alignment["flag"]
        reference = alignment["reference"]
        position = alignment["position"]
        cigar = alignment["cigar"]
        span = cigar_reference_span(cigar)
        end = position + span - 1
        for locus in loci:
            if not _overlaps_locus(reference, position, end, locus):
                continue
            locus_qnames.add(qname)
            if require_umi_tags:
                ug = resolved_ug.get(qname)
                bx = resolved_bx.get(qname)
                if not ug or not bx:
                    continue
                group_key = ug
                bx_by_group[group_key].add(bx)
            else:
                group_key = qname
            intervals = parse_intervals(locus["reference_intervals"])
            mapped = cigar_mapped_bases_in_locus(position, cigar, intervals)
            key = (group_key, locus["locus_id"])
            record = groups.setdefault(
                key,
                {
                    "locus": locus,
                    "read_count": 0,
                    "mapped_bases": 0,
                    "proper_qnames": set(),
                    "discordant_qnames": set(),
                    "qnames": set(),
                },
            )
            record["read_count"] += 1
            record["mapped_bases"] += mapped
            record["qnames"].add(qname)
            if flag & 0x2:
                record["proper_qnames"].add(qname)
            if bool(flag & 0x1) and not bool(flag & 0x2):
                record["discordant_qnames"].add(qname)

    if require_umi_tags:
        missing = sorted(
            qname for qname in locus_qnames
            if qname not in resolved_ug or qname not in resolved_bx
        )
        if missing:
            raise ValueError(
                f"{sam_path}: umi_tools group BAM missing UG/BX tags for QNAME(s): "
                + ", ".join(missing)
            )
        for group_key, values in bx_by_group.items():
            if len(values) != 1:
                raise ValueError(
                    f"inconsistent BX tags for UG={group_key}: {sorted(values)}"
                )

    rows: list[dict] = []
    umi_group_method = "directional" if require_umi_tags else "none"
    for (group_key, locus_id), record in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        locus = record["locus"]
        qname_digests = sorted(sha256_text(name) for name in record["qnames"])
        source_digests = ";".join(qname_digests)
        template_count = len(record["qnames"])
        if require_umi_tags:
            final_umi = next(iter(bx_by_group[group_key]))
            lineage_id = _lineage_id(run_id, sample_id, final_umi, qname_digests)
            eligible = "true"
            rejection_reason = ""
        else:
            final_umi = ""
            lineage_id = ""
            eligible = "false"
            rejection_reason = "MISSING_FIELD"
        record_payload = "\0".join([
            run_id, sample_id, group_key, locus_id, lineage_id, final_umi, source_digests,
        ])
        rows.append({
            "lineage_record_id": _lineage_record_id(record_payload),
            "lineage_id": lineage_id,
            "sample_id": sample_id,
            "reference_id": locus["sseqid"],
            "locus_id": locus_id,
            "orientation": locus.get("orientation", ""),
            "query_ids": locus.get("query_ids", ""),
            "source_template_digests": source_digests,
            "final_umi": final_umi,
            "umi_group_method": umi_group_method,
            "library_mode": library_mode,
            "umi_mode": umi_mode,
            "template_count": template_count,
            "read_count": record["read_count"],
            "mapped_bases": record["mapped_bases"],
            "proper_pair_templates": len(record["proper_qnames"]),
            "discordant_templates": len(record["discordant_qnames"]),
            "eligible": eligible,
            "rejection_reason": rejection_reason,
            "rule_id": "ADMIT-TEMPLATE-LINEAGE",
        })
    return rows


def write_header_only(path: str | Path) -> None:
    write_tsv_atomic(path, [], FIELDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build factual template_lineage.tsv from mapped reads")
    parser.add_argument("--sam", help="SAM/SAM-from-group BAM text for lineage metrics")
    parser.add_argument("--loci", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--library-mode", default="unknown")
    parser.add_argument("--umi-mode", default="none")
    parser.add_argument(
        "--header-only",
        action="store_true",
        help="Write header-only TSV when remapping is skipped upstream",
    )
    args = parser.parse_args()
    if args.header_only:
        write_header_only(args.out)
        return
    if not args.sam:
        parser.error("--sam is required unless --header-only is set")
    if not args.loci:
        parser.error("--loci is required unless --header-only is set")
    loci = read_tsv(args.loci) if Path(args.loci).is_file() else []
    require_umi = args.umi_mode != "none"
    rows = build_rows_from_sam(
        args.sam,
        run_id=args.run_id,
        sample_id=args.sample,
        library_mode=args.library_mode,
        umi_mode=args.umi_mode,
        loci=loci,
        require_umi_tags=require_umi,
    )
    write_tsv_atomic(args.out, rows, FIELDS)


if __name__ == "__main__":
    main()
