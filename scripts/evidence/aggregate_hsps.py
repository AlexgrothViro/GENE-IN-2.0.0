#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import os
import shutil
import signal
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

try:
    from .common import (
        format_intervals, interval_size, merge_intervals, read_fasta,
        sequence_metrics, sha256_text, write_tsv_atomic,
    )
    from .line_sort import iter_merged, reduce_runs
except ImportError:
    from common import (
        format_intervals, interval_size, merge_intervals, read_fasta,
        sequence_metrics, sha256_text, write_tsv_atomic,
    )
    from line_sort import iter_merged, reduce_runs


BLAST_COLUMNS = (
    "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
    "qstart", "qend", "sstart", "send", "evalue", "bitscore", "qlen", "slen",
    "nident", "gaps",
)

FIELDS = [
    "qseqid", "sseqid", "task", "category", "taxon", "segment", "orientation",
    "qlen", "slen", "hsp_count", "query_intervals", "reference_intervals",
    "query_covered_bp", "reference_covered_bp", "query_coverage", "weighted_pident",
    "identity_covered_bp",
    "best_evalue", "best_bitscore", "sum_bitscore", "adj_identity_raw", "adj_identity",
    "integrity_flags", "sequence_sha256", "sequence_entropy", "n_fraction",
    "max_homopolymer_fraction", "low_complexity_status", "assembly_method",
]
LABEL_CATEGORIES = {
    "TARGET_VIRUS", "NEAR_NON_TARGET_VIRUS", "HOST", "VECTOR_ADAPTER",
    "KNOWN_CONTAMINANT", "SYNTHETIC_SEQUENCE", "UNLABELED",
}


def union_weighted_identity(hsps: list[dict]) -> tuple[float, int]:
    """Estimate identity over non-redundant query positions only.

    BLAST can emit overlapping HSPs for the same query.  Sorting by query
    interval and then preferring the stronger HSP makes the assignment
    deterministic while ensuring an overlap contributes once to the
    aggregate identity.
    """
    covered: list[tuple[int, int]] = []
    weighted = 0.0
    unique_bp = 0
    ordered = sorted(
        hsps,
        key=lambda h: (
            -h["bitscore"], h["evalue"], -h["pident"],
            min(h["qstart"], h["qend"]), max(h["qstart"], h["qend"]),
            min(h["sstart"], h["send"]), max(h["sstart"], h["send"]),
        ),
    )
    for hsp in ordered:
        start, end = sorted((hsp["qstart"], hsp["qend"]))
        if start > end:
            continue
        novel = end - start + 1
        for old_start, old_end in covered:
            overlap_start = max(start, old_start)
            overlap_end = min(end, old_end)
            if overlap_start <= overlap_end:
                novel -= overlap_end - overlap_start + 1
        novel = max(novel, 0)
        if novel:
            weighted += hsp["pident"] * novel
            unique_bp += novel
            covered = merge_intervals([*covered, (start, end)])
    return (weighted / unique_bp if unique_bp else 0.0, unique_bp)


def load_labels(path: str | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"sseqid", "category"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("subject labels require sseqid and category columns")
        labels: dict[str, dict[str, str]] = {}
        for line_number, row in enumerate(reader, 2):
            subject = row.get("sseqid", "")
            category = row.get("category", "")
            if not subject:
                raise ValueError(f"{path}:{line_number}: empty subject label")
            if category not in LABEL_CATEGORIES:
                raise ValueError(
                    f"{path}:{line_number}: invalid subject category: {category!r}"
                )
            if subject in labels:
                raise ValueError(f"{path}:{line_number}: duplicate subject label: {subject}")
            labels[subject] = row
    return labels


def _finite_number(value: str, field: str, path: str | Path, line_number: int) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{path}:{line_number}: invalid numeric BLAST field {field}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{path}:{line_number}: non-finite BLAST field {field}")
    return number


def parse_blast_line(raw: str, path: str | Path, line_number: int, task: str) -> dict:
    cols = raw.rstrip("\n").split("\t")
    if len(cols) == 14:
        raise ValueError(
            f"{path}:{line_number}: rejected legacy 14-column BLAST outfmt; "
            "canonical format requires 16 columns ending with nident gaps"
        )
    if len(cols) != 16:
        raise ValueError(
            f"{path}:{line_number}: expected the canonical 16-column BLAST outfmt"
        )
    try:
        qstart, qend, sstart, send = map(int, cols[6:10])
        length = int(cols[3])
        mismatch = int(cols[4])
        gapopen = int(cols[5])
        qlen = int(cols[12])
        slen = int(cols[13])
        nident = int(cols[14])
        gaps = int(cols[15])
    except ValueError as exc:
        raise ValueError(f"{path}:{line_number}: invalid numeric BLAST field") from exc
    pident = _finite_number(cols[2], "pident", path, line_number)
    evalue = _finite_number(cols[10], "evalue", path, line_number)
    bitscore = _finite_number(cols[11], "bitscore", path, line_number)
    if not cols[0] or not cols[1]:
        raise ValueError(f"{path}:{line_number}: empty BLAST sequence identifier")
    if not 0.0 <= pident <= 100.0:
        raise ValueError(f"{path}:{line_number}: pident is outside 0..100")
    if (
        length < 1 or mismatch < 0 or gapopen < 0 or qlen < 1 or slen < 1
        or nident < 0 or gaps < 0
    ):
        raise ValueError(f"{path}:{line_number}: invalid BLAST lengths or counts")
    if nident + mismatch + gaps != length:
        raise ValueError(
            f"{path}:{line_number}: nident + mismatch + gaps must equal alignment length"
        )
    if evalue < 0.0 or bitscore < 0.0:
        raise ValueError(f"{path}:{line_number}: negative BLAST score")
    if min(qstart, qend, sstart, send) < 1:
        raise ValueError(f"{path}:{line_number}: BLAST coordinates must be positive")
    if max(qstart, qend) > qlen or max(sstart, send) > slen:
        raise ValueError(f"{path}:{line_number}: BLAST coordinates exceed sequence length")
    return {
        "qseqid": cols[0], "sseqid": cols[1], "pident": pident,
        "length": length, "mismatch": mismatch, "gapopen": gapopen,
        "qstart": qstart, "qend": qend, "sstart": sstart, "send": send,
        "evalue": evalue, "bitscore": bitscore, "qlen": qlen,
        "slen": slen, "nident": nident, "gaps": gaps, "task": task,
        "raw_fields": list(cols),
    }


def iter_blast(path: str | Path, task: str):
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            yield parse_blast_line(raw, path, line_number, task)


def parse_blast(path: str | Path, task: str) -> list[dict]:
    # Public list API retained for existing callers and tests.
    return list(iter_blast(path, task))


# Hits of one query stay in memory up to this count. Beyond it, that query is
# sorted on disk by subject group. The bound tracks the longest query, not the
# whole BLAST report.
QUERY_HITS_IN_RAM = 100_000
_ROW_CHUNK = 8_000
_RAW_CHUNK = 50_000
_MERGE_FANOUT = 64
_SPACE_FLOOR = 512 * 1024 * 1024
_GIB = 1024 ** 3


class RepeatedQuery(Exception):
    """A query id returned after another query, so the file is not grouped."""


class AggregationDiskError(RuntimeError):
    """Free space is below the aggregation estimate or the runtime floor."""


def _format_gib(value: int) -> str:
    return f"{value / _GIB:.1f}".replace(".", ",") + " GiB"


def _segment_of(hit: dict, labels: dict) -> str:
    return labels.get(hit["sseqid"], {}).get("segment", "unsegmented") or "unsegmented"


def _orientation_of(hit: dict) -> str:
    return "+" if (hit["qend"] - hit["qstart"]) * (hit["send"] - hit["sstart"]) >= 0 else "-"


def aggregation_space_estimate(input_bytes: int, *, sort_raw_lines: bool = False) -> int:
    """Upper bound used before writing.

    Contiguous BLAST reports are aggregated one query at a time. On the real
    AMOSTRA01 retest almost every HSP stayed its own aggregated row, and that
    row is wider than the BLAST line (about 330 B against about 130 B). The
    temporary runs then hold one copy of the aggregated table and the atomic
    write holds another. Six times the BLAST text plus 1 GiB covers that on
    one filesystem. A report that is not grouped by query also sorts the
    original lines, so the estimate gains one more copy of the input.
    """
    factor = 7 if sort_raw_lines else 6
    return input_bytes * factor + _GIB


def require_aggregation_space(
    work_dir: Path,
    output_dir: Path,
    input_bytes: int,
    *,
    sort_raw_lines: bool = False,
) -> None:
    needed = aggregation_space_estimate(input_bytes, sort_raw_lines=sort_raw_lines)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    same_device = os.stat(work_dir).st_dev == os.stat(output_dir).st_dev
    checks = [(work_dir, needed)] if same_device else [
        (work_dir, input_bytes * (4 if sort_raw_lines else 3) + _GIB),
        (output_dir, input_bytes * 3 + _GIB),
    ]
    for directory, required in checks:
        free = shutil.disk_usage(directory).free
        if free < required:
            raise AggregationDiskError(
                "Espaço livre insuficiente para agregar os HSPs. "
                f"Estimativa desta etapa: {_format_gib(required)} "
                f"({_format_gib(input_bytes)} de relatórios BLAST, "
                "com margem para a tabela agregada e a gravação da saída). "
                f"Espaço livre em {directory}: {_format_gib(free)}. "
                "Libere espaço em disco e execute novamente."
            )


def _guard_free_space(directory: Path) -> None:
    free = shutil.disk_usage(directory).free
    if free < _SPACE_FLOOR:
        raise AggregationDiskError(
            "Espaço livre insuficiente durante a agregação dos HSPs. "
            f"Espaço livre em {directory}: {_format_gib(free)}. "
            "A etapa foi interrompida antes de encher o disco."
        )


def _row_key(row: dict) -> tuple:
    return (row["qseqid"], row["sseqid"], row["task"], row["segment"], row["orientation"])


def _encode_aggregated_row(index: int, row: dict) -> str:
    values = [str(index)]
    for field in FIELDS:
        value = row.get(field, "")
        text = "" if value is None else str(value)
        if "\t" in text or "\n" in text or "\r" in text:
            raise ValueError(f"aggregated field {field} contains a tab or line break")
        values.append(text)
    return "\t".join(values) + "\n"


def _aggregated_line_key(line: str) -> tuple:
    head = line.split("\t", 8)
    return (head[1], head[2], head[3], head[6], head[7], int(head[0]))


def _decode_aggregated_row(line: str) -> dict:
    parts = line.rstrip("\n").split("\t")
    expected = 1 + len(FIELDS)
    if len(parts) != expected:
        raise ValueError(f"aggregated row has {len(parts)} columns, expected {expected}")
    return dict(zip(FIELDS, parts[1:]))


class _RowChunks:
    """Stable external sort of aggregated rows by the historical group key.

    Rows are stored as TSV, not JSON. On a sample where each HSP stays its own
    row, the JSON form was several times larger than the output table.
    """

    def __init__(self, directory: Path):
        self.directory = directory
        self.paths: list[Path] = []
        self.buffer: list[tuple[int, dict]] = []
        self.sequence = 0

    def add_rows(self, rows) -> None:
        for row in rows:
            self.buffer.append((self.sequence, row))
            self.sequence += 1
            if len(self.buffer) >= _ROW_CHUNK:
                self.flush()
                _guard_free_space(self.directory)

    def flush(self) -> None:
        if not self.buffer:
            return
        self.buffer.sort(key=lambda item: (*_row_key(item[1]), item[0]))
        path = self.directory / f"rows-{len(self.paths):05d}.tsv"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for index, row in self.buffer:
                handle.write(_encode_aggregated_row(index, row))
        self.paths.append(path)
        self.buffer.clear()

    def sorted_rows(self):
        self.flush()
        if not self.paths:
            return
        runs = reduce_runs(
            self.paths, self.directory, "rows", _aggregated_line_key,
            lambda: _guard_free_space(self.directory),
        )
        self.paths = runs
        for line in iter_merged(runs, _aggregated_line_key):
            yield _decode_aggregated_row(line)


def _iter_lines(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from handle


def _external_record_key(line: str) -> tuple:
    qseqid, ordinal, _line_number, _raw = line.split("\t", 3)
    return (qseqid, int(ordinal))


def _write_merged_lines(paths: list[Path], dest: Path, key_fn) -> None:
    handles = [path.open("r", encoding="utf-8", newline="") for path in paths]
    try:
        with dest.open("w", encoding="utf-8", newline="") as output:
            for line in heapq.merge(*handles, key=key_fn):
                output.write(line if line.endswith("\n") else line + "\n")
    finally:
        for handle in handles:
            handle.close()


def _merge_line_files(paths: list[Path], directory: Path, prefix: str, key_fn) -> Path:
    pending = list(paths)
    generation = 0
    while len(pending) > 1:
        generation += 1
        if len(pending) <= _MERGE_FANOUT:
            dest = directory / f"{prefix}-final.tsv"
            _write_merged_lines(pending, dest, key_fn)
            return dest
        reduced: list[Path] = []
        for index in range(0, len(pending), _MERGE_FANOUT):
            batch = pending[index:index + _MERGE_FANOUT]
            if len(batch) == 1:
                reduced.append(batch[0])
                continue
            dest = directory / f"{prefix}-m{generation}-{len(reduced):05d}.tsv"
            _write_merged_lines(batch, dest, key_fn)
            reduced.append(dest)
            _guard_free_space(directory)
        pending = reduced
    return pending[0]


class _QueryAggregator:
    """Aggregate one query, spilling subject groups when the query is long."""

    def __init__(self, qseqid: str, task: str, directory: Path, labels: dict, index: int):
        self.qseqid = qseqid
        self.task = task
        self.directory = directory
        self.labels = labels
        self.index = index
        self.memory: list[dict] = []
        self.spilled = False
        self.chunks: list[Path] = []
        self.bucket: list[tuple] = []
        self.ordinal = 0
        self.spill_dir: Path | None = None

    def add(self, hit: dict) -> None:
        if not self.spilled:
            self.memory.append(hit)
            if len(self.memory) <= QUERY_HITS_IN_RAM:
                return
            self.spilled = True
            self.spill_dir = self.directory / f"query-{self.index:05d}"
            self.spill_dir.mkdir(parents=True, exist_ok=True)
            pending = self.memory
            self.memory = []
            for kept in pending:
                self._append_compact(kept)
            return
        self._append_compact(hit)

    def _append_compact(self, hit: dict) -> None:
        key = (hit["sseqid"], _segment_of(hit, self.labels), _orientation_of(hit), self.ordinal)
        self.bucket.append((key, "\t".join(hit["raw_fields"])))
        self.ordinal += 1
        if len(self.bucket) >= _RAW_CHUNK:
            self._flush_bucket()

    def _flush_bucket(self) -> None:
        if not self.bucket or self.spill_dir is None:
            return
        self.bucket.sort()
        path = self.spill_dir / f"part-{len(self.chunks):05d}.tsv"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for key, raw in self.bucket:
                handle.write("\t".join(key[:3]) + f"\t{key[3]}\t{raw}\n")
        self.chunks.append(path)
        self.bucket.clear()
        _guard_free_space(self.spill_dir)

    def rows(self, sequences, assembly_method: str) -> list[dict]:
        if not self.spilled:
            return aggregate(self.memory, sequences, self.labels, assembly_method)
        self._flush_bucket()
        assert self.spill_dir is not None

        def sort_key(line: str) -> tuple:
            sseqid, segment, orientation, ordinal, _raw = line.split("\t", 4)
            return (sseqid, segment, orientation, int(ordinal))

        merged_path = _merge_line_files(self.chunks, self.spill_dir, "groups", sort_key)
        grouped: list[dict] = []
        output: list[dict] = []
        current: tuple | None = None
        with merged_path.open("r", encoding="utf-8", newline="") as handle:
            for line in handle:
                sseqid, segment, orientation, _ordinal, raw = line.rstrip("\n").split("\t", 4)
                key = (sseqid, segment, orientation)
                hit = parse_blast_line(raw, merged_path, 1, self.task)
                if current is None:
                    current = key
                if key != current:
                    output.extend(aggregate(grouped, sequences, self.labels, assembly_method))
                    grouped = []
                    current = key
                grouped.append(hit)
        if grouped:
            output.extend(aggregate(grouped, sequences, self.labels, assembly_method))
        return output


def split_reference_clusters(hsps: list[dict]) -> list[list[dict]]:
    """Keep disconnected subject regions separate until locus construction."""
    ordered = sorted(
        hsps,
        key=lambda h: (
            min(h["sstart"], h["send"]), max(h["sstart"], h["send"]),
            min(h["qstart"], h["qend"]), max(h["qstart"], h["qend"]),
        ),
    )
    clusters: list[list[dict]] = []
    cluster_end = 0
    for hsp in ordered:
        start, end = sorted((hsp["sstart"], hsp["send"]))
        if not clusters or start > cluster_end + 1:
            clusters.append([hsp])
            cluster_end = end
        else:
            clusters[-1].append(hsp)
            cluster_end = max(cluster_end, end)
    return clusters


def dedupe_exact_hsps(records: list[dict]) -> list[dict]:
    """Drop exact-equivalent raw HSPs (same task + raw_fields) before clustering."""
    seen: set[tuple] = set()
    unique: list[dict] = []
    for hit in records:
        raw = hit.get("raw_fields")
        if raw is not None:
            key: tuple = (hit["task"], tuple(raw))
        else:
            key = (
                hit["task"], hit["qseqid"], hit["sseqid"], hit["pident"], hit["length"],
                hit["mismatch"], hit["gapopen"], hit["qstart"], hit["qend"],
                hit["sstart"], hit["send"], hit["evalue"], hit["bitscore"],
                hit["qlen"], hit["slen"], hit.get("nident"), hit.get("gaps"),
            )
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique


def aggregate(
    records: list[dict],
    sequences: dict[str, str],
    labels: dict[str, dict[str, str]],
    assembly_method: str = "",
) -> list[dict]:
    records = dedupe_exact_hsps(records)
    grouped = defaultdict(list)
    for hit in records:
        if sequences:
            if hit["qseqid"] not in sequences:
                raise ValueError(f"BLAST query is absent from query FASTA: {hit['qseqid']}")
            if len(sequences[hit["qseqid"]]) != hit["qlen"]:
                raise ValueError(
                    f"BLAST qlen disagrees with query FASTA for {hit['qseqid']}"
                )
        orientation = "+" if (hit["qend"] - hit["qstart"]) * (hit["send"] - hit["sstart"]) >= 0 else "-"
        label = labels.get(hit["sseqid"], {})
        segment = label.get("segment", "unsegmented") or "unsegmented"
        key = (hit["qseqid"], hit["sseqid"], hit["task"], segment, orientation)
        grouped[key].append(hit)

    rows = []
    for (qseqid, sseqid, task, segment, orientation), grouped_hsps in sorted(grouped.items()):
        qlens = {h["qlen"] for h in grouped_hsps}
        slens = {h["slen"] for h in grouped_hsps}
        if len(qlens) != 1:
            raise ValueError(f"inconsistent qlen values for {qseqid}")
        if len(slens) != 1:
            raise ValueError(f"inconsistent slen values for {sseqid}")
        qlen = next(iter(qlens))
        slen = next(iter(slens))
        for hsps in split_reference_clusters(grouped_hsps):
            q_intervals = merge_intervals((h["qstart"], h["qend"]) for h in hsps)
            s_intervals = merge_intervals((h["sstart"], h["send"]) for h in hsps)
            q_covered = interval_size(q_intervals)
            s_covered = interval_size(s_intervals)
            weighted_pident, identity_covered_bp = union_weighted_identity(hsps)
            qcov = q_covered / qlen if qlen else 0.0
            raw_adj = weighted_pident * qcov
            flags = []
            if raw_adj > 100.0:
                flags.append("ADJ_IDENTITY_CLAMPED")
            if q_covered > qlen > 0:
                flags.append("QUERY_UNION_EXCEEDS_QLEN")
            sequence = sequences.get(qseqid, "")
            metrics = sequence_metrics(sequence)
            low_complexity = metrics["entropy"] < 1.2 or metrics["max_homopolymer_fraction"] > 0.60
            label = labels.get(sseqid, {})
            rows.append({
                "qseqid": qseqid, "sseqid": sseqid, "task": task,
                "category": label.get("category", "UNLABELED"), "taxon": label.get("taxon", ""),
                "segment": segment, "orientation": orientation, "qlen": qlen, "slen": slen,
                "hsp_count": len(hsps), "query_intervals": format_intervals(q_intervals),
                "reference_intervals": format_intervals(s_intervals), "query_covered_bp": q_covered,
                "reference_covered_bp": s_covered, "query_coverage": f"{qcov:.6f}",
                "weighted_pident": f"{weighted_pident:.6f}",
                "identity_covered_bp": identity_covered_bp,
                "best_evalue": f"{min(h['evalue'] for h in hsps):.8g}",
                "best_bitscore": f"{max(h['bitscore'] for h in hsps):.6f}",
                "sum_bitscore": f"{sum(h['bitscore'] for h in hsps):.6f}",
                "adj_identity_raw": f"{raw_adj:.6f}", "adj_identity": f"{min(raw_adj, 100.0):.6f}",
                "integrity_flags": ";".join(flags) or "OK",
                "sequence_sha256": sha256_text(sequence) if sequence else "",
                "sequence_entropy": f"{metrics['entropy']:.6f}", "n_fraction": f"{metrics['n_fraction']:.6f}",
                "max_homopolymer_fraction": f"{metrics['max_homopolymer_fraction']:.6f}",
                "low_complexity_status": "LOW_COMPLEXITY" if low_complexity else "ACCEPTABLE",
                "assembly_method": assembly_method,
            })
    return rows


def _feed_query(collector: _QueryAggregator | None, rows: _RowChunks, sequences, assembly_method: str) -> None:
    if collector is not None:
        rows.add_rows(collector.rows(sequences, assembly_method))


def _aggregate_contiguous(path: Path, task: str, sequences, labels, assembly_method: str,
                          rows: _RowChunks, directory: Path, index: int) -> int:
    seen: set[str] = set()
    current: str | None = None
    collector: _QueryAggregator | None = None
    for hit in iter_blast(path, task):
        qseqid = hit["qseqid"]
        if current is None:
            current = qseqid
            collector = _QueryAggregator(qseqid, task, directory, labels, index)
            index += 1
        elif qseqid != current:
            if qseqid in seen:
                raise RepeatedQuery
            seen.add(current)
            _feed_query(collector, rows, sequences, assembly_method)
            current = qseqid
            collector = _QueryAggregator(qseqid, task, directory, labels, index)
            index += 1
        assert collector is not None
        collector.add(hit)
    if current is not None and current in seen:
        raise RepeatedQuery
    _feed_query(collector, rows, sequences, assembly_method)
    return index


def _aggregate_reordered(paths: list[Path], task: str, sequences, labels, assembly_method: str,
                         rows: _RowChunks, directory: Path, index: int) -> int:
    """Sort reports that revisit queries, then aggregate one query at a time.

    Ordinals increase across the paths in the order given, matching the
    historical chain of inputs.
    """
    raw_dir = directory / f"reordered-{index:05d}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []
    bucket: list[tuple[str, int, int, str, str]] = []
    ordinal = 0

    def flush() -> None:
        nonlocal bucket
        if not bucket:
            return
        bucket.sort()
        dest = raw_dir / f"raw-{len(chunks):05d}.tsv"
        with dest.open("w", encoding="utf-8", newline="\n") as handle:
            for qseqid, ordinal_value, line_number, source, raw in bucket:
                handle.write(f"{qseqid}\t{ordinal_value}\t{line_number}\t{source}\t{raw}\n")
        chunks.append(dest)
        bucket = []
        _guard_free_space(raw_dir)

    for source_index, path in enumerate(paths):
        with path.open("r", encoding="utf-8", errors="strict") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                hit = parse_blast_line(raw, path, line_number, task)
                bucket.append((hit["qseqid"], ordinal, line_number, str(source_index), "\t".join(hit["raw_fields"])))
                ordinal += 1
                if len(bucket) >= _RAW_CHUNK:
                    flush()
    flush()
    if not chunks:
        return index
    merged = _merge_line_files(chunks, raw_dir, "by-query", _external_record_key)
    collector: _QueryAggregator | None = None
    with merged.open("r", encoding="utf-8", newline="") as handle:
        for line in handle:
            _qseqid, _ordinal, line_number, source_index, raw = line.rstrip("\n").split("\t", 4)
            source = paths[int(source_index)]
            hit = parse_blast_line(raw, source, int(line_number), task)
            if collector is None or hit["qseqid"] != collector.qseqid:
                _feed_query(collector, rows, sequences, assembly_method)
                collector = _QueryAggregator(hit["qseqid"], task, directory, labels, index)
                index += 1
            collector.add(hit)
    _feed_query(collector, rows, sequences, assembly_method)
    return index


def _aggregate_file(path: Path, task: str, sequences, labels, assembly_method: str,
                    rows: _RowChunks, directory: Path, index: int,
                    work_dir: Path, output_dir: Path, input_bytes: int) -> int:
    rows.flush()
    start_paths = len(rows.paths)
    start_sequence = rows.sequence
    try:
        return _aggregate_contiguous(
            path, task, sequences, labels, assembly_method, rows, directory, index,
        )
    except RepeatedQuery:
        for chunk in rows.paths[start_paths:]:
            chunk.unlink(missing_ok=True)
        del rows.paths[start_paths:]
        rows.buffer.clear()
        rows.sequence = start_sequence
        for child in directory.glob("query-*"):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
        require_aggregation_space(work_dir, output_dir, input_bytes, sort_raw_lines=True)
        return _aggregate_reordered(
            [path], task, sequences, labels, assembly_method, rows, directory, index,
        )


def write_fragment_evidence(inputs: list[tuple[str, Path]], out: Path, sequences: dict,
                            labels: dict, assembly_method: str = "", work_dir: Path | None = None,
                            query_metadata: dict | None = None) -> None:
    """Aggregate BLAST reports into fragment_evidence.tsv.

    Reports already grouped by query are aggregated in one pass. The temporary
    files store the aggregated rows as TSV, not a JSON copy of every HSP. The
    output order remains the historical (query, subject, task, segment,
    orientation) order, with input order as the tie break.
    """
    output = Path(out)
    workspace = Path(work_dir) if work_dir is not None else output.parent
    workspace.mkdir(parents=True, exist_ok=True)
    input_bytes = sum(Path(path).stat().st_size for _task, path in inputs)
    require_aggregation_space(workspace, output.parent, input_bytes)
    with tempfile.TemporaryDirectory(prefix="genein-hsps-", dir=workspace) as tmp_name:
        directory = Path(tmp_name)
        rows = _RowChunks(directory)
        index = 0
        grouped_inputs: dict[str, list[Path]] = {}
        for task, path in inputs:
            grouped_inputs.setdefault(task, []).append(Path(path))
        for task, paths in grouped_inputs.items():
            if len(paths) == 1:
                index = _aggregate_file(
                    paths[0], task, sequences, labels, assembly_method, rows, directory,
                    index, workspace, output.parent, input_bytes,
                )
                continue
            rows.flush()
            require_aggregation_space(workspace, output.parent, input_bytes, sort_raw_lines=True)
            index = _aggregate_reordered(
                paths, task, sequences, labels, assembly_method, rows, directory, index,
            )
        _guard_free_space(workspace)

        def produced():
            for row in rows.sorted_rows():
                if query_metadata:
                    sources = query_metadata[row["qseqid"]]["source_counts"]
                    if not ({"contig", "assembled_short"} & set(sources)):
                        row["assembly_method"] = "read_level"
                yield row

        write_tsv_atomic(output, produced(), FIELDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate overlapping BLAST HSPs without inflating evidence")
    parser.add_argument("--blast", action="append", required=True, metavar="TASK=PATH")
    parser.add_argument("--query-fasta")
    parser.add_argument("--query-manifest")
    parser.add_argument("--subject-labels")
    parser.add_argument(
        "--assembly-method",
        default="",
        help="Assembler used for query contigs (ASSEMBLER_USED); empty if unknown",
    )
    parser.add_argument("--work-dir", help="Directory for aggregation temporary files. Defaults to the output directory.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    inputs = []
    for spec in args.blast:
        if "=" not in spec:
            parser.error("--blast must use TASK=PATH")
        task, path = spec.split("=", 1)
        if task not in {"blastn", "blastn-short"}:
            parser.error(f"unsupported BLAST task: {task}")
        inputs.append((task, Path(path)))
    sequences = read_fasta(args.query_fasta) if args.query_fasta else {}
    query_metadata = {}
    if args.query_manifest:
        manifest = json.loads(Path(args.query_manifest).read_text(encoding="utf-8"))
        query_metadata = manifest["queries"]
        if set(query_metadata) != set(sequences):
            raise ValueError("candidate manifest and query FASTA have different IDs")
        for query_id, entry in query_metadata.items():
            if entry["sequence_sha256"] != sha256_text(sequences[query_id]):
                raise ValueError(f"candidate manifest sequence mismatch: {query_id}")
    try:
        write_fragment_evidence(
            inputs, Path(args.out), sequences, load_labels(args.subject_labels),
            args.assembly_method, Path(args.work_dir) if args.work_dir else None,
            query_metadata or None,
        )
    except AggregationDiskError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    def terminate(signum, _frame):
        # Unwind TemporaryDirectory on external termination.
        # SIGKILL cannot be handled by any process.
        print(
            f"[ERRO] Agregação de HSPs interrompida por {signal.Signals(signum).name}.",
            file=sys.stderr,
        )
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
