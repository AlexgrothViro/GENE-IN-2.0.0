#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
from collections import defaultdict

try:
    from .common import parse_intervals, read_fasta, read_tsv, write_tsv_atomic
except ImportError:
    from common import parse_intervals, read_fasta, read_tsv, write_tsv_atomic


FIELDS = [
    "reference_id", "category", "locus_id", "orientation", "query_ids",
    "reference_length", "locus_length", "covered_bases_1x", "covered_bases_3x",
    "breadth_1x", "breadth_3x", "mean_depth_locus", "median_depth_covered",
    "min_depth_covered", "max_window_depth_fraction", "concentration_window_bp",
    "minimum_mapq", "minimum_base_quality",
]


def concentration_fraction(depths: list[int], window_bp: int) -> float:
    total = sum(depths)
    if total <= 0:
        return 0.0
    width = min(max(window_bp, 1), len(depths))
    current = sum(depths[:width])
    maximum = current
    for idx in range(width, len(depths)):
        current += depths[idx] - depths[idx - width]
        maximum = max(maximum, current)
    return maximum / total


def load_loci(path: str | None, lengths: dict[str, int]) -> list[dict[str, str]]:
    if path:
        rows = read_tsv(path)
        required = {"locus_id", "sseqid", "category", "orientation", "query_ids", "reference_intervals"}
        if rows and not required.issubset(rows[0]):
            raise ValueError(f"locus table missing columns: {', '.join(sorted(required - set(rows[0])))}")
        return rows
    return [{
        "locus_id": f"REFERENCE::{reference}", "sseqid": reference, "category": "UNLABELED",
        "orientation": "", "query_ids": "", "reference_intervals": f"1-{length}",
    } for reference, length in lengths.items()]


def summarize(depth_by_ref: dict[str, dict[int, int]], lengths: dict[str, int], loci: list[dict[str, str]],
              window_bp: int, minimum_mapq: int, minimum_base_quality: int) -> list[dict]:
    rows = []
    seen: set[tuple[str, str, str]] = set()
    for locus in sorted(loci, key=lambda row: (row["sseqid"], row["category"], row["locus_id"])):
        reference = locus["sseqid"]
        if reference not in lengths:
            raise ValueError(f"locus {locus['locus_id']} references unknown sequence {reference}")
        key = (reference, locus["category"], locus["locus_id"])
        if key in seen:
            raise ValueError(f"duplicate locus metric key: {key}")
        seen.add(key)
        coordinates: list[int] = []
        for left, right in parse_intervals(locus["reference_intervals"]):
            if left < 1 or right > lengths[reference]:
                raise ValueError(f"locus {locus['locus_id']} interval outside reference bounds")
            coordinates.extend(range(left, right + 1))
        if not coordinates:
            raise ValueError(f"locus {locus['locus_id']} has no covered coordinates")
        positions = depth_by_ref.get(reference, {})
        depths = [positions.get(pos, 0) for pos in coordinates]
        covered = [value for value in depths if value > 0]
        covered_1x = len(covered)
        covered_3x = sum(value >= 3 for value in depths)
        locus_length = len(depths)
        rows.append({
            "reference_id": reference, "category": locus["category"], "locus_id": locus["locus_id"],
            "orientation": locus.get("orientation", ""), "query_ids": locus.get("query_ids", ""),
            "reference_length": lengths[reference], "locus_length": locus_length,
            "covered_bases_1x": covered_1x, "covered_bases_3x": covered_3x,
            "breadth_1x": f"{covered_1x / locus_length:.8f}",
            "breadth_3x": f"{covered_3x / locus_length:.8f}",
            "mean_depth_locus": f"{sum(depths) / locus_length:.8f}",
            "median_depth_covered": f"{statistics.median(covered) if covered else 0.0:.8f}",
            "min_depth_covered": min(covered) if covered else 0,
            "max_window_depth_fraction": f"{concentration_fraction(depths, window_bp):.8f}",
            "concentration_window_bp": window_bp, "minimum_mapq": minimum_mapq,
            "minimum_base_quality": minimum_base_quality,
        })
    return rows


def parse_depth(path: str) -> dict[str, dict[int, int]]:
    result: dict[str, dict[int, int]] = defaultdict(dict)
    with open(path, "r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            cols = raw.rstrip("\r\n").split("\t")
            if len(cols) != 3:
                raise ValueError(f"{path}:{line_number}: expected exactly 3 depth columns")
            reference, position_text, depth_text = cols
            try:
                position, depth = int(position_text), int(depth_text)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid numeric depth field") from exc
            if position < 1 or depth < 0:
                raise ValueError(f"{path}:{line_number}: invalid depth coordinate or value")
            if position in result[reference]:
                raise ValueError(f"{path}:{line_number}: duplicate depth coordinate {reference}:{position}")
            result[reference][position] = depth
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize coverage within each candidate locus")
    parser.add_argument("--depth", required=True)
    parser.add_argument("--reference-fasta", required=True)
    parser.add_argument("--loci")
    parser.add_argument("--out", required=True)
    parser.add_argument("--window-bp", type=int, default=100)
    parser.add_argument("--minimum-mapq", type=int, default=10)
    parser.add_argument("--minimum-base-quality", type=int, default=20)
    args = parser.parse_args()
    lengths = {name: len(seq) for name, seq in read_fasta(args.reference_fasta).items()}
    loci = load_loci(args.loci, lengths)
    write_tsv_atomic(args.out, summarize(parse_depth(args.depth), lengths, loci, args.window_bp,
                                         args.minimum_mapq, args.minimum_base_quality), FIELDS)


if __name__ == "__main__":
    main()
