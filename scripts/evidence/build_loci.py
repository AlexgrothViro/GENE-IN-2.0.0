#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import signal
import sys
import tempfile
from pathlib import Path
from collections import defaultdict

try:
    from .common import as_float, as_int, format_intervals, interval_size, merge_intervals, parse_intervals, iter_tsv, write_tsv_atomic
    from .disk_space import EvidenceDiskError, guard_floor, require_step_space
    from .line_sort import LineSorter, iter_merged
except ImportError:
    from common import as_float, as_int, format_intervals, interval_size, merge_intervals, parse_intervals, iter_tsv, write_tsv_atomic
    from disk_space import EvidenceDiskError, guard_floor, require_step_space
    from line_sort import LineSorter, iter_merged


FIELDS = [
    "locus_id", "sseqid", "taxon", "category", "segment", "orientation", "task",
    "query_intervals", "query_covered_bp", "reference_intervals", "reference_start", "reference_end", "covered_reference_bp",
    "reference_length", "reference_breadth", "query_ids", "query_count", "unique_sequence_count",
    "hsp_count", "best_bitscore", "sum_bitscore", "best_adj_identity", "best_evalue",
    "max_query_length", "max_query_covered_bp", "low_complexity_queries", "coord_system",
]


def _build_group(group_key, items, gap_bp):
    sseqid, segment, orientation, task = group_key
    items.sort(key=lambda item: (item[0], item[1]))
    clusters = []
    cluster_end = None
    for item in items:
        if cluster_end is None or item[0] > cluster_end + gap_bp + 1:
            clusters.append([item])
            cluster_end = item[1]
        else:
            clusters[-1].append(item)
            cluster_end = max(cluster_end, item[1])
    for cluster in clusters:
        intervals = merge_intervals((x[0], x[1]) for x in cluster)
        cluster_rows = list({id(x[2]): x[2] for x in cluster}.values())
        query_intervals_by_id: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for row in cluster_rows:
            query_intervals_by_id[row["qseqid"]].extend(
                parse_intervals(row.get("query_intervals", ""))
            )
        merged_query_intervals = {
            query_id: merge_intervals(values)
            for query_id, values in query_intervals_by_id.items()
        }
        query_covered_by_id = {
            query_id: interval_size(values)
            for query_id, values in merged_query_intervals.items()
        }
        query_ids = sorted({r["qseqid"] for r in cluster_rows})
        hashes = {r["sequence_sha256"] for r in cluster_rows if r.get("sequence_sha256")}
        covered = interval_size(intervals)
        slen = max((as_int(r.get("slen")) for r in cluster_rows), default=0)
        digest = hashlib.sha256(
            f"{sseqid}|{segment}|{orientation}|{task}|{format_intervals(intervals)}".encode("utf-8")
        ).hexdigest()[:12]
        yield {
            "locus_id": f"LOCUS_{digest}", "sseqid": sseqid,
            "taxon": cluster_rows[0].get("taxon", ""), "category": cluster_rows[0].get("category", "UNLABELED"),
            "segment": segment, "orientation": orientation, "task": task,
            "reference_intervals": format_intervals(intervals), "reference_start": intervals[0][0],
            "reference_end": intervals[-1][1], "covered_reference_bp": covered,
            "query_intervals": "|".join(
                f"{query_id}:{format_intervals(merged_query_intervals[query_id])}"
                for query_id in query_ids
            ),
            "query_covered_bp": sum(query_covered_by_id.values()),
            "reference_length": slen, "reference_breadth": f"{covered / slen if slen else 0.0:.8f}",
            "query_ids": ";".join(query_ids), "query_count": len(query_ids),
            "unique_sequence_count": len(hashes) if hashes else len(query_ids),
            "hsp_count": sum(as_int(r.get("hsp_count"), 1) for r in cluster_rows),
            "best_bitscore": f"{max(as_float(r.get('best_bitscore')) for r in cluster_rows):.6f}",
            "sum_bitscore": f"{sum(as_float(r.get('sum_bitscore'), as_float(r.get('best_bitscore'))) for r in cluster_rows):.6f}",
            "best_adj_identity": f"{max(as_float(r.get('adj_identity')) for r in cluster_rows):.6f}",
            "best_evalue": f"{min(as_float(r.get('best_evalue'), 1.0) for r in cluster_rows):.8g}",
            "max_query_length": max(as_int(r.get("qlen")) for r in cluster_rows),
            "max_query_covered_bp": max(query_covered_by_id.values(), default=0),
            "low_complexity_queries": sum(r.get("low_complexity_status") == "LOW_COMPLEXITY" for r in cluster_rows),
            "coord_system": "1-based-inclusive",
        }


def build_loci(rows: list[dict[str, str]], gap_bp: int = 100, categories: set[str] | None = None) -> list[dict]:
    categories = categories or {"TARGET_VIRUS", "UNLABELED"}
    buckets = defaultdict(list)
    for row in rows:
        if row.get("category", "UNLABELED") not in categories:
            continue
        key = (row["sseqid"], row.get("segment", "unsegmented"), row.get("orientation", "+"), row.get("task", "blastn"))
        for start, end in parse_intervals(row["reference_intervals"]):
            buckets[key].append((start, end, row))
    return [locus for key, items in sorted(buckets.items()) for locus in _build_group(key, items, gap_bp)]


# Columns carried into the sort line, in this order, after the interval key.
_PAYLOAD_FIELDS = (
    "qseqid", "query_intervals", "sequence_sha256", "slen", "hsp_count",
    "best_bitscore", "sum_bitscore", "adj_identity", "best_evalue", "qlen",
    "low_complexity_status", "taxon", "category",
)
_GIB = 1024 ** 3


def loci_space_estimate(fragment_bytes: int) -> tuple[int, int]:
    """Return (temporary bytes, output bytes).

    Interval runs are at most about the size of the fragment table. The locus
    table on the AMOSTRA01 retest was smaller than that table; half of it plus
    1 GiB is the output reserve.
    """
    temporary = fragment_bytes + _GIB
    output = max(_GIB, fragment_bytes // 2)
    return temporary, output


def _plain(value: object, field: str) -> str:
    text = "" if value is None else str(value)
    if "\t" in text or "\n" in text or "\r" in text:
        raise ValueError(f"locus field {field} contains a tab or line break")
    return text


def _interval_line(row: dict, start: int, end: int, row_id: int) -> str:
    head = [
        _plain(row["sseqid"], "sseqid"),
        _plain(row.get("segment", "unsegmented"), "segment"),
        _plain(row.get("orientation", "+"), "orientation"),
        _plain(row.get("task", "blastn"), "task"),
        str(start), str(end), str(row_id),
    ]
    payload = {}
    for field in _PAYLOAD_FIELDS:
        if field in row and row[field] is not None:
            payload[field] = row[field]
    return "\t".join(head) + "\t" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _locus_line_key(line: str) -> tuple:
    parts = line.split("\t", 7)
    return (parts[0], parts[1], parts[2], parts[3], int(parts[4]), int(parts[5]), int(parts[6]))


def _row_from_line(line: str) -> dict:
    payload = line.rstrip("\n").split("\t", 7)[7]
    return json.loads(payload)


def _loci_from_runs(runs: list[Path], gap_bp: int):
    current = None
    items: list[tuple[int, int, dict]] = []
    row_cache: dict[int, dict] = {}

    def emit():
        if current is not None:
            yield from _build_group(current, items, gap_bp)

    for line in iter_merged(runs, _locus_line_key):
        parts = line.split("\t", 7)
        key = (parts[0], parts[1], parts[2], parts[3])
        if key != current:
            yield from emit()
            current = key
            items = []
            row_cache = {}
        row_id = int(parts[6])
        row = row_cache.get(row_id)
        if row is None:
            row = _row_from_line(line)
            row_cache[row_id] = row
        items.append((int(parts[4]), int(parts[5]), row))
    yield from emit()


def build_loci_disk(path: str | Path, gap_bp: int = 100, categories: set[str] | None = None,
                    work_dir: str | Path | None = None, output_dir: str | Path | None = None):
    """Build loci one reference/segment/strand/task group at a time.

    Intervals are sorted as compact lines in the run directory. The full
    fragment row is not copied into SQLite.
    """
    categories = categories or {"TARGET_VIRUS", "UNLABELED"}
    source = Path(path)
    workspace = Path(work_dir) if work_dir is not None else (Path(output_dir) if output_dir is not None else source.parent)
    destination = Path(output_dir) if output_dir is not None else workspace
    temporary, output = loci_space_estimate(source.stat().st_size)
    require_step_space(workspace, destination, temporary, output, "construir os loci")
    with tempfile.TemporaryDirectory(prefix="genein-loci-", dir=workspace) as tmp:
        directory = Path(tmp)

        def guard() -> None:
            guard_floor(directory, "construir os loci")

        sorter = LineSorter(directory, "intervals", _locus_line_key, guard)
        for row_id, row in enumerate(iter_tsv(source), 1):
            if row.get("category", "UNLABELED") not in categories:
                continue
            for start, end in parse_intervals(row["reference_intervals"]):
                sorter.add(_interval_line(row, start, end, row_id))
        yield from _loci_from_runs(sorter.finish(), gap_bp)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build independent viral loci from aggregated HSPs")
    parser.add_argument("--fragments", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--gap-bp", type=int, default=100)
    parser.add_argument("--categories", default="TARGET_VIRUS,UNLABELED")
    parser.add_argument("--work-dir", help="Directory for locus temporary files. Defaults to the output directory.")
    args = parser.parse_args()
    if args.gap_bp < 0:
        parser.error("--gap-bp must be non-negative")
    out = Path(args.out)
    try:
        rows = build_loci_disk(
            args.fragments, args.gap_bp, set(args.categories.split(",")),
            Path(args.work_dir) if args.work_dir else out.parent, out.parent,
        )
        write_tsv_atomic(out, rows, FIELDS)
    except EvidenceDiskError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    def terminate(signum, _frame):
        # Unwind TemporaryDirectory on external termination.
        # SIGKILL cannot be handled by any process.
        print(
            f"[ERRO] Construção de loci interrompida por {signal.Signals(signum).name}.",
            file=sys.stderr,
        )
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
