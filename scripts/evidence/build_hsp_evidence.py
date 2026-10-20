#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import signal
import sqlite3
import sys
import tempfile
from itertools import chain
from collections import defaultdict
from pathlib import Path

try:
    from .aggregate_hsps import BLAST_COLUMNS, iter_blast
    from .common import configure_csv_field_limit, parse_intervals, write_tsv_atomic
    from .disk_space import EvidenceDiskError, guard_floor, require_step_space
    from .line_sort import LineSorter, iter_merged
except ImportError:
    from aggregate_hsps import BLAST_COLUMNS, iter_blast
    from common import configure_csv_field_limit, parse_intervals, write_tsv_atomic
    from disk_space import EvidenceDiskError, guard_floor, require_step_space
    from line_sort import LineSorter, iter_merged


FIELDS = [
    "hsp_id", "duplicate_of_hsp_id", "qseqid", "sseqid", "task",
    "query_start", "query_end", "subject_start", "subject_end",
    "alignment_length", "identity_pct", "matches", "mismatches", "gaps",
    "gap_openings", "evalue", "bitscore", "strand", "coord_system",
    "query_length", "subject_length", "locus_id", "eligible",
    "rejection_reason", "rule_id",
]


def _orientation(hit: dict) -> str:
    return "+" if (hit["qend"] - hit["qstart"]) * (hit["send"] - hit["sstart"]) >= 0 else "-"


def _subject_interval(hit: dict) -> tuple[int, int]:
    return sorted((hit["sstart"], hit["send"]))


def _interval_contained(inner: tuple[int, int], outer_intervals: list[tuple[int, int]]) -> bool:
    start, end = inner
    return any(start >= left and end <= right for left, right in outer_intervals)


def _hsp_id(task: str, raw_fields: list[str], ordinal: int) -> str:
    payload = "\0".join([task, *raw_fields, str(ordinal)])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"HSP_{digest}"


def _duplicate_key(task: str, raw_fields: list[str]) -> tuple[str, ...]:
    return (task, *raw_fields)


class LocusIndex:
    """Index query membership while retaining subject groups with no query match."""

    def __init__(self, loci: list[dict[str, str]]):
        self.groups = set()
        self.candidates = defaultdict(list)
        self.intervals = {}
        for ordinal, locus in enumerate(loci):
            group = (locus.get("sseqid"), locus.get("task"), locus.get("orientation"))
            self.groups.add(group)
            for query in set(filter(None, locus.get("query_ids", "").split(";"))):
                self.candidates[(*group, query)].append((ordinal, locus))


def _query_ids(value):
    """Yield memberships without allocating a split list or a set."""
    start = 0
    while start < len(value):
        end = value.find(";", start)
        if end < 0:
            end = len(value)
        if end > start:
            yield value[start:end]
        start = end + 1


class DiskLocusIndex:
    """Store memberships on disk, retaining only one input TSV row at a time."""

    def __init__(self, db, loci):
        self.db = db
        db.execute("CREATE TABLE locus_groups (g TEXT PRIMARY KEY) WITHOUT ROWID")
        db.execute("CREATE TABLE loci (ordinal INTEGER PRIMARY KEY, locus_id TEXT, intervals TEXT)")
        db.execute("CREATE TABLE memberships (g TEXT, query TEXT, ordinal INTEGER, "
                   "PRIMARY KEY (g, query, ordinal)) WITHOUT ROWID")
        for ordinal, locus in enumerate(loci):
            group = json.dumps((locus.get("sseqid"), locus.get("task"), locus.get("orientation")))
            db.execute("INSERT OR IGNORE INTO locus_groups VALUES (?)", (group,))
            db.execute("INSERT INTO loci VALUES (?,?,?)", (
                ordinal, locus["locus_id"], locus.get("reference_intervals", "")))
            db.executemany("INSERT OR IGNORE INTO memberships VALUES (?,?,?)", (
                (group, query, ordinal) for query in _query_ids(locus.get("query_ids", ""))))
            if ordinal % 1000 == 999:
                db.commit()
        db.commit()

    def has_group(self, group):
        return self.db.execute("SELECT 1 FROM locus_groups WHERE g=?", (json.dumps(group),)).fetchone() is not None

    def candidates_for(self, group, query):
        cursor = self.db.execute(
            "SELECT l.ordinal, l.locus_id, l.intervals FROM memberships m "
            "JOIN loci l ON l.ordinal=m.ordinal WHERE m.g=? AND m.query=? ORDER BY m.ordinal",
            (json.dumps(group), query))
        for ordinal, locus_id, intervals in cursor:
            yield ordinal, {"sseqid": group[0], "task": group[1], "orientation": group[2],
                            "locus_id": locus_id, "reference_intervals": intervals}


def iter_loci(path):
    configure_csv_field_limit()
    with Path(path).open("r", encoding="utf-8", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"TSV has no header: {path}")
        yield from reader


def associate_locus(hit: dict, loci: list[dict[str, str]] | LocusIndex | DiskLocusIndex) -> tuple[str | None, str | None]:
    """Return (locus_id, rejection_reason).

    Exactly one contained match → assign. Multiple matches → hard fail.
    Zero matches with same sseqid/task/orientation present → hard fail
    (containment/query membership broken). Zero matches and no locus for
    that subject grouping → OUT_OF_DECLARED_SCOPE (e.g. HOST outside loci).
    """
    orientation = _orientation(hit)
    subject = _subject_interval(hit)
    matches: list[str] = []
    indexed = isinstance(loci, LocusIndex)
    group = (hit["sseqid"], hit["task"], orientation)
    if isinstance(loci, DiskLocusIndex):
        same_key = loci.has_group(group)
        candidates = loci.candidates_for(group, hit["qseqid"])
    else:
        same_key = group in loci.groups if indexed else False
        candidates = loci.candidates.get((*group, hit["qseqid"]), ()) if indexed else enumerate(loci)
    for ordinal, locus in candidates:
        if locus.get("sseqid") != hit["sseqid"]:
            continue
        if locus.get("task") != hit["task"]:
            continue
        if locus.get("orientation") != orientation:
            continue
        same_key = True
        if isinstance(loci, DiskLocusIndex):
            intervals = parse_intervals(locus.get("reference_intervals", ""))
        elif indexed:
            if ordinal not in loci.intervals:
                loci.intervals[ordinal] = parse_intervals(locus.get("reference_intervals", ""))
            intervals = loci.intervals[ordinal]
        else:
            query_ids = {item for item in locus.get("query_ids", "").split(";") if item}
            if hit["qseqid"] not in query_ids:
                continue
            intervals = parse_intervals(locus.get("reference_intervals", ""))
        if _interval_contained(subject, intervals):
            matches.append(locus["locus_id"])
    if len(matches) > 1:
        raise ValueError(
            f"HSP {hit['qseqid']}/{hit['sseqid']}/{hit['task']} subject "
            f"{subject[0]}-{subject[1]} matches {len(matches)} loci "
            f"(require exactly one); candidates={matches}"
        )
    if len(matches) == 1:
        return matches[0], None
    if same_key:
        raise ValueError(
            f"HSP {hit['qseqid']}/{hit['sseqid']}/{hit['task']} subject "
            f"{subject[0]}-{subject[1]} matches 0 loci "
            f"(require exactly one); candidates=[]"
        )
    return None, "OUT_OF_DECLARED_SCOPE"


def iter_hsp_evidence(records, loci, ordinals):
    locus_index = loci if isinstance(loci, (LocusIndex, DiskLocusIndex)) else LocusIndex(loci)
    for hit in records:
        matches = hit["nident"]
        mismatches = hit["mismatch"]
        gaps = hit["gaps"]
        alignment_length = hit["length"]
        if matches + mismatches + gaps != alignment_length:
            raise ValueError(
                f"matches + mismatches + gaps must equal alignment_length "
                f"for {hit['qseqid']}/{hit['sseqid']}"
            )
        raw_fields = hit.get("raw_fields")
        if not raw_fields or len(raw_fields) != len(BLAST_COLUMNS):
            raise ValueError("HSP evidence requires the 16 raw BLAST field strings")
        key = _duplicate_key(hit["task"], raw_fields)
        ordinal = ordinals[key]
        ordinals[key] = ordinal + 1
        hsp_id = _hsp_id(hit["task"], raw_fields, ordinal)
        is_duplicate = ordinal > 0
        locus_id, scope_reason = associate_locus(hit, locus_index)
        if is_duplicate:
            eligible = "false"
            rejection_reason = "DUPLICATE_SOURCE_OBSERVATION"
        elif scope_reason:
            eligible = "false"
            rejection_reason = scope_reason
        else:
            eligible = "true"
            rejection_reason = ""
        yield {
            "hsp_id": hsp_id,
            "duplicate_of_hsp_id": _hsp_id(hit["task"], raw_fields, 0) if is_duplicate else "",
            "qseqid": hit["qseqid"],
            "sseqid": hit["sseqid"],
            "task": hit["task"],
            "query_start": hit["qstart"],
            "query_end": hit["qend"],
            "subject_start": hit["sstart"],
            "subject_end": hit["send"],
            "alignment_length": alignment_length,
            "identity_pct": hit["pident"],
            "matches": matches,
            "mismatches": mismatches,
            "gaps": gaps,
            "gap_openings": hit["gapopen"],
            "evalue": hit["evalue"],
            "bitscore": hit["bitscore"],
            "strand": _orientation(hit),
            "coord_system": "1-based-inclusive",
            "query_length": hit["qlen"],
            "subject_length": hit["slen"],
            "locus_id": locus_id or "",
            "eligible": eligible,
            "rejection_reason": rejection_reason,
            "rule_id": "ADMIT-HSP",
        }


def build_hsp_evidence(records: list[dict], loci: list[dict[str, str]]) -> list[dict]:
    return list(iter_hsp_evidence(records, loci, defaultdict(int)))


_GIB = 1024 ** 3


def hsp_space_estimate(blast_bytes: int, locus_bytes: int) -> tuple[int, int]:
    """Return (temporary bytes, output bytes).

    Duplicate ordinals are a hash of the raw line, not the line stored as JSON.
    The output table on the AMOSTRA01 retest was about 1.7 times the BLAST text.
    """
    temporary = blast_bytes + locus_bytes + _GIB
    output = blast_bytes * 2 + _GIB
    return temporary, output


def _observation_token(task: str, raw_fields: list[str]) -> str:
    return hashlib.sha256("\0".join((task, *raw_fields)).encode("utf-8")).hexdigest()


def _require_raw(hit: dict) -> list[str]:
    raw_fields = hit.get("raw_fields")
    if not raw_fields or len(raw_fields) != len(BLAST_COLUMNS):
        raise ValueError("HSP evidence requires the 16 raw BLAST field strings")
    return raw_fields


def _token_key(line: str) -> tuple:
    seq, token = line.split("\t", 1)
    return (token.rstrip("\n"), int(seq))


def _seq_key(line: str) -> tuple:
    seq, _ordinal = line.split("\t", 1)
    return (int(seq),)


class _OrdinalStream:
    """Return precomputed duplicate ordinals in BLAST encounter order."""

    def __init__(self, lines):
        self._lines = iter(lines)

    def __getitem__(self, _key):
        try:
            line = next(self._lines)
        except StopIteration as exc:
            raise ValueError("ordinal stream ended before the BLAST records") from exc
        _seq, ordinal = line.split("\t", 1)
        return int(ordinal)

    def __setitem__(self, _key, _value):
        return None


def _iter_hits(inputs: list[tuple[str, Path]]):
    return chain.from_iterable(iter_blast(path, task) for task, path in inputs)


def build_hsp_evidence_disk(inputs: list[tuple[str, Path]], loci_path: str | Path,
                            work_dir: str | Path | None = None,
                            output_dir: str | Path | None = None):
    """Emit HSP rows without storing every raw line as a SQLite key."""
    locus_file = Path(loci_path)
    workspace = Path(work_dir) if work_dir is not None else (Path(output_dir) if output_dir is not None else locus_file.parent)
    destination = Path(output_dir) if output_dir is not None else workspace
    blast_bytes = sum(Path(path).stat().st_size for _task, path in inputs)
    locus_bytes = locus_file.stat().st_size if locus_file.is_file() else 0
    temporary, output = hsp_space_estimate(blast_bytes, locus_bytes)
    require_step_space(workspace, destination, temporary, output, "montar a evidência por HSP")
    with tempfile.TemporaryDirectory(prefix="genein-hsp-ids-", dir=workspace) as tmp:
        directory = Path(tmp)

        def guard() -> None:
            guard_floor(directory, "montar a evidência por HSP")

        tokens = LineSorter(directory, "obs", _token_key, guard)
        for seq, hit in enumerate(_iter_hits(inputs)):
            tokens.add(f"{seq}\t{_observation_token(hit['task'], _require_raw(hit))}\n")
        token_runs = tokens.finish()
        ordinal_path = directory / "ordinals.tsv"
        previous = None
        count = 0
        with ordinal_path.open("w", encoding="utf-8", newline="\n") as handle:
            for line in iter_merged(token_runs, _token_key):
                seq, token = line.split("\t", 1)
                token = token.rstrip("\n")
                if token != previous:
                    previous = token
                    count = 0
                else:
                    count += 1
                handle.write(f"{seq}\t{count}\n")
        for path in token_runs:
            path.unlink(missing_ok=True)
        guard()
        ordinals = LineSorter(directory, "ord", _seq_key, guard)
        with ordinal_path.open("r", encoding="utf-8", newline="") as handle:
            for line in handle:
                ordinals.add(line)
        ordinal_path.unlink(missing_ok=True)
        db = sqlite3.connect(str(directory / "loci.sqlite"))
        try:
            db.execute("PRAGMA journal_mode=OFF").fetchall()
            db.execute("PRAGMA synchronous=OFF").fetchall()
            db.execute("PRAGMA temp_store=MEMORY").fetchall()
            db.execute("PRAGMA cache_size=-8192").fetchall()
            locus_rows = iter_loci(locus_file) if locus_file.is_file() else []
            locus_index = DiskLocusIndex(db, locus_rows)
            yield from iter_hsp_evidence(
                _iter_hits(inputs), locus_index, _OrdinalStream(iter_merged(ordinals.finish(), _seq_key)),
            )
        finally:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit one factual HSP row per raw BLAST observation")
    parser.add_argument("--blast", action="append", required=True, metavar="TASK=PATH")
    parser.add_argument("--loci", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work-dir", help="Directory for HSP temporary files. Defaults to the output directory.")
    args = parser.parse_args()
    inputs = []
    for spec in args.blast:
        if "=" not in spec:
            parser.error("--blast must use TASK=PATH")
        task, path = spec.split("=", 1)
        if task not in {"blastn", "blastn-short"}:
            parser.error(f"unsupported BLAST task: {task}")
        inputs.append((task, Path(path)))
    out = Path(args.out)
    try:
        write_tsv_atomic(
            out,
            build_hsp_evidence_disk(
                inputs, args.loci,
                Path(args.work_dir) if args.work_dir else out.parent,
                out.parent,
            ),
            FIELDS,
        )
    except EvidenceDiskError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    def terminate(signum, _frame):
        # Unwind TemporaryDirectory on external termination.
        # SIGKILL cannot be handled by any process.
        print(
            f"[ERRO] Evidência de HSP interrompida por {signal.Signals(signum).name}.",
            file=sys.stderr,
        )
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
