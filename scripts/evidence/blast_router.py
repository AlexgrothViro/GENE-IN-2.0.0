#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from .activation_policy import load_public_activation_policy
    from .common import (blast_db_arg, fsync_directory, read_fasta, replace_atomic, sha256_file,
                         write_json_atomic, write_text_atomic)
except ImportError:
    from activation_policy import load_public_activation_policy
    from common import (blast_db_arg, fsync_directory, read_fasta, replace_atomic, sha256_file,
                        write_json_atomic, write_text_atomic)


OUTFMT = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
IUPAC_NUCLEOTIDES = frozenset("ACGTRYSWKMBDHVN")
SHORT_QUERY_BLOCK_SIZE = 256


def external_blast_exit(returncode: int) -> int:
    """Preserve SIGKILL/SIGTERM instead of letting Python collapse them to exit 1."""
    if returncode < 0:
        return 128 - returncode
    return returncode


def run_external_blast(command: list[str]) -> None:
    completed = subprocess.run(command, check=False)
    if completed.returncode == 0:
        return
    if completed.returncode < 0:
        signum = -completed.returncode
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        print(f"[ERRO] blastn encerrado por {name}.", file=sys.stderr)
        raise SystemExit(external_blast_exit(completed.returncode))
    raise subprocess.CalledProcessError(completed.returncode, command)


def profiles_for_length(length: int, config: dict, recover_short_fragments=False) -> tuple[str, ...]:
    blast = config["blast"]
    if recover_short_fragments and 20 <= length <= 100:
        return ("short",) if length <= int(blast["short_max_bp"]) else ("short", "conventional")
    if length <= int(blast["short_max_bp"]):
        return ("short",)
    if int(blast["dual_mode_min_bp"]) <= length <= int(blast["dual_mode_max_bp"]):
        return ("short", "conventional")
    return ("conventional",)


def profile_parameters(config: dict, max_target_seqs: int = 50) -> dict[str, dict[str, object]]:
    blast = config["blast"]
    shared = {
        "gapopen": 5, "gapextend": 2, "evalue": 1000,
        "max_target_seqs": max_target_seqs,
        "dust": "yes" if blast["explicit_dust"] else "no",
        "soft_masking": "true" if blast["soft_masking"] else "false",
    }
    return {
        "short": {**shared, "task": "blastn-short", "word_size": 7, "reward": 1, "penalty": -3},
        "conventional": {**shared, "task": "blastn", "word_size": 11, "reward": 2, "penalty": -3},
    }


def write_fasta(path: Path, records: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8", errors="strict", newline="\n") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n{sequence}\n")


def validate_nucleotide_queries(sequences: dict[str, str]) -> None:
    if not sequences:
        raise ValueError("query FASTA contains no sequences")
    for name, sequence in sequences.items():
        if not sequence:
            raise ValueError(f"query FASTA contains an empty sequence: {name}")
        invalid = sorted(set(sequence.upper()) - IUPAC_NUCLEOTIDES)
        if invalid:
            raise ValueError(
                f"query {name!r} contains non-nucleotide symbols: {''.join(invalid)}"
            )


def database_sequence_count(database: str, blastdbcmd: str) -> int:
    result = subprocess.run(
        [blastdbcmd, "-db", blast_db_arg(database), "-info"],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"([\d,]+)\s+sequences?;", result.stdout)
    if not match:
        raise ValueError("unable to determine BLAST database sequence count")
    count = int(match.group(1).replace(",", ""))
    if count < 1:
        raise ValueError("BLAST database contains no sequences")
    return count


def database_report_limit(database: str, blastdbcmd: str | None = None,
                          *, sequence_count: int | None = None) -> int:
    """Return a search limit that does not truncate a competitive panel."""
    if sequence_count is None:
        if not blastdbcmd:
            raise ValueError("blastdbcmd is required when sequence_count is not provided")
        sequence_count = database_sequence_count(database, blastdbcmd)
    if sequence_count < 1:
        raise ValueError("BLAST database contains no sequences")
    return max(50, sequence_count)


def _hit_key_rank(line: str) -> tuple[tuple[object, ...], tuple[object, ...]]:
    """Same key/rank as deduplicate_combined_hits, for one 16-column line."""
    fields = line.split("\t")
    if len(fields) != 16:
        raise ValueError("BLAST output does not match the configured 16-column outfmt")
    qstart, qend, sstart, send = map(int, (fields[6], fields[7], fields[8], fields[9]))
    bitscore, evalue, pident = float(fields[11]), float(fields[10]), float(fields[2])
    key = (
        fields[0], fields[1],
        "+" if (qend - qstart) * (send - sstart) >= 0 else "-",
        min(qstart, qend), max(qstart, qend),
        min(sstart, send), max(sstart, send),
    )
    return key, (-bitscore, evalue, -pident, line)


def _rank_is_better(new_bitscore, new_evalue, new_pident, new_line,
                    old_bitscore, old_evalue, old_pident, old_line) -> bool:
    """True when the new rank is strictly smaller, matching tuple order."""
    return (
        (-float(new_bitscore), float(new_evalue), -float(new_pident), new_line)
        < (-float(old_bitscore), float(old_evalue), -float(old_pident), old_line)
    )


def _iter_hit_lines(paths: list[Path]):
    """Yield BLAST lines in file order, without a trailing break.

    Universal newlines match str.splitlines() for the breaks BLAST writes
    (\\n, \\r and \\r\\n), including a blank line and a final line without a break.
    """
    for path in paths:
        with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
            for raw in handle:
                if raw.endswith("\n"):
                    raw = raw[:-1]
                if raw.endswith("\r"):
                    raw = raw[:-1]
                yield raw


_DEDUP_INSERT = """
INSERT INTO hits (
    qseqid, sseqid, strand, qmin, qmax, smin, smax,
    bitscore, evalue, pident, line, first_ordinal
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT (qseqid, sseqid, strand, qmin, qmax, smin, smax) DO UPDATE SET
    bitscore = excluded.bitscore,
    evalue = excluded.evalue,
    pident = excluded.pident,
    line = excluded.line
WHERE rank_is_better(
    excluded.bitscore, excluded.evalue, excluded.pident, excluded.line,
    hits.bitscore, hits.evalue, hits.pident, hits.line
)
"""


def _write_deduped_lines(lines, handle) -> None:
    """Keep the best line per coordinate key; emit keys in first-seen order.

    The table lives on disk. Only one input line and a small insert batch
    are in memory. first_ordinal is the position of the key's first line and
    is never replaced, so a later stronger hit keeps the original slot.
    """
    with tempfile.TemporaryDirectory(prefix="genein-blast-dedup-") as tmp_name:
        db = sqlite3.connect(str(Path(tmp_name) / "hits.sqlite"))
        try:
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("PRAGMA cache_size=-32768")
            db.create_function("rank_is_better", 8, _rank_is_better)
            db.execute(
                """
                CREATE TABLE hits (
                    qseqid TEXT NOT NULL,
                    sseqid TEXT NOT NULL,
                    strand TEXT NOT NULL,
                    qmin INTEGER NOT NULL,
                    qmax INTEGER NOT NULL,
                    smin INTEGER NOT NULL,
                    smax INTEGER NOT NULL,
                    bitscore REAL NOT NULL,
                    evalue REAL NOT NULL,
                    pident REAL NOT NULL,
                    line TEXT NOT NULL,
                    first_ordinal INTEGER NOT NULL,
                    PRIMARY KEY (qseqid, sseqid, strand, qmin, qmax, smin, smax)
                ) WITHOUT ROWID
                """
            )
            batch = []
            for ordinal, line in enumerate(lines):
                key, rank = _hit_key_rank(line)
                batch.append((*key, -rank[0], rank[1], -rank[2], line, ordinal))
                if len(batch) >= 5000:
                    db.executemany(_DEDUP_INSERT, batch)
                    batch.clear()
            if batch:
                db.executemany(_DEDUP_INSERT, batch)
            db.commit()
            for (line,) in db.execute("SELECT line FROM hits ORDER BY first_ordinal"):
                handle.write(line)
                handle.write("\n")
        finally:
            db.close()


def deduplicate_hit_files(paths: list[Path], combined_out: Path) -> None:
    """Stream profile TSVs into one deduplicated report."""
    combined_out = Path(combined_out)
    combined_out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{combined_out.name}.", suffix=".tmp", dir=combined_out.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            _write_deduped_lines(_iter_hit_lines(paths), handle)
            handle.flush()
            os.fsync(handle.fileno())
        replace_atomic(tmp_path, combined_out)
        fsync_directory(combined_out.parent)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def deduplicate_combined_hits(chunks: list[str]) -> str:
    """Keep the strongest exact-coordinate hit emitted by dual BLAST profiles."""
    with tempfile.TemporaryDirectory(prefix="genein-blast-dedup-") as tmp_name:
        tmp = Path(tmp_name)
        spool = tmp / "joined.tsv"
        with spool.open("w", encoding="utf-8", newline="") as handle:
            for chunk in chunks:
                handle.write(chunk)
        out = tmp / "dedup.tsv"
        deduplicate_hit_files([spool], out)
        return out.read_text(encoding="utf-8")


def _atomic_text_handle(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    return Path(tmp_name), os.fdopen(fd, "w", encoding="utf-8", newline="")


def _commit_atomic(tmp: Path, handle, target: Path) -> None:
    handle.flush()
    os.fsync(handle.fileno())
    handle.close()
    replace_atomic(tmp, target)
    fsync_directory(target.parent)


def copy_text_atomic(source: Path, target: Path) -> None:
    """Streaming equivalent of write_text_atomic(target, source.read_text())."""
    tmp, handle = _atomic_text_handle(Path(target))
    try:
        with Path(source).open("r", encoding="utf-8", errors="strict") as reader:
            shutil.copyfileobj(reader, handle, 1 << 20)
        _commit_atomic(tmp, handle, Path(target))
    finally:
        if not handle.closed:
            handle.close()
        if tmp.exists():
            tmp.unlink()


def deduplicate_combined_files(paths: list[Path], query_order: list[str], combined_out: Path) -> None:
    """Keep the existing file API, with disk dedup independent of query order.

    query_order remains accepted by current callers; SQLite preserves the
    first-seen coordinate-key order even for interleaved/rewritten query ids.
    No raw report or single-query hit group is materialized in memory.
    """
    deduplicate_hit_files(paths, combined_out)


def run_router(query: str, database: str, config: dict, threads: int,
               short_out: Path | None, conventional_out: Path | None,
               combined_out: Path | None, recover_short_fragments=False) -> dict:
    executable = shutil.which("blastn")
    if not executable:
        raise RuntimeError("blastn is not available")
    blastdbcmd = shutil.which("blastdbcmd")
    if not blastdbcmd:
        raise RuntimeError("blastdbcmd is not available")
    if threads < 1:
        raise ValueError("threads must be positive")
    sequences = read_fasta(query)
    validate_nucleotide_queries(sequences)
    sequence_count = database_sequence_count(database, blastdbcmd)
    grouped: dict[str, list[tuple[str, str]]] = {"short": [], "conventional": []}
    assignments = []
    for name, sequence in sequences.items():
        profiles = profiles_for_length(len(sequence), config, recover_short_fragments)
        assignments.append({"query_id": name, "length": len(sequence), "profiles": list(profiles)})
        for profile in profiles:
            grouped[profile].append((name, sequence))
    # Specificity needs the whole competitive panel, not an arbitrary top-N
    # report.  The effective report limit therefore covers every DB subject.
    parameters = profile_parameters(
        config,
        database_report_limit(database, sequence_count=sequence_count),
    )
    outputs = {"short": short_out, "conventional": conventional_out}
    combined_paths: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="genein-blast-router-") as tmp_name:
        tmp = Path(tmp_name)
        for profile in ("short", "conventional"):
            target = outputs[profile]
            records = grouped[profile]
            if not records:
                continue
            query_path = tmp / f"{profile}.fa"
            result_path = tmp / f"{profile}.tsv"
            write_fasta(query_path, records)
            values = parameters[profile]
            command = [
                executable, "-task", str(values["task"]), "-query", str(query_path), "-db", blast_db_arg(database),
                "-outfmt", OUTFMT, "-word_size", str(values["word_size"]),
                "-reward", str(values["reward"]), "-penalty", str(values["penalty"]),
                "-gapopen", str(values["gapopen"]), "-gapextend", str(values["gapextend"]),
                "-dust", str(values["dust"]), "-soft_masking", str(values["soft_masking"]),
                "-max_target_seqs", str(values["max_target_seqs"]), "-evalue", str(values["evalue"]),
                "-num_threads", str(threads), "-out", str(result_path),
            ]
            if profile == "short":
                # Queries are independent; retain their order and every search
                # parameter. Bound BLAST's resident query/alignment batch.
                block_result = tmp / "short.block.tsv"
                with result_path.open("wb") as destination:
                    for start in range(0, len(records), SHORT_QUERY_BLOCK_SIZE):
                        write_fasta(query_path, records[start:start + SHORT_QUERY_BLOCK_SIZE])
                        block_command = list(command)
                        block_command[-1] = str(block_result)
                        run_external_blast(block_command)
                        with block_result.open("rb") as source:
                            shutil.copyfileobj(source, destination, 1 << 20)
            else:
                run_external_blast(command)
            # Never load the raw BLAST report into memory: with evalue=1000 and
            # max_target_seqs=<all subjects>, read-level searches emit tens of
            # millions of rows (several GB), which was killed by the OOM killer.
            if target:
                copy_text_atomic(result_path, target)
            combined_paths.append(result_path)
        for profile, target in outputs.items():
            if target and not grouped[profile]:
                write_text_atomic(target, "")
        if combined_out:
            deduplicate_combined_files(combined_paths, list(sequences), combined_out)
    database_path = Path(database)
    database_files = sorted(
        path for path in database_path.parent.glob(database_path.name + ".*") if path.is_file()
    )
    version = subprocess.run([executable, "-version"], capture_output=True, text=True, check=False)
    version_lines = (version.stdout or version.stderr).splitlines()
    return {
        "router_schema": "1.0", "blastn_version": version_lines[0] if version_lines else "UNKNOWN",
        "routing_policy": "fragment_recovery_20_100_v1" if recover_short_fragments else "activation_profile",
        "database_prefix": str(database_path.resolve()),
        "database_sequence_count": sequence_count,
        "report_limit_covers_database": True,
        "database_components": {
            str(path.resolve()): {"size": path.stat().st_size, "sha256": sha256_file(path)}
            for path in database_files
        },
        "profiles": parameters, "assignments": assignments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the canonical length-routed BLAST search")
    parser.add_argument("--query", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--activation-policy")
    parser.add_argument("--profiles")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--out-short", type=Path)
    parser.add_argument("--out-conventional", type=Path)
    parser.add_argument("--out-combined", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--recover-short-fragments", action="store_true",
                        help="Additionally search all 20–100 bp queries with blastn-short; record the new routing policy")
    args = parser.parse_args()
    if not any((args.out_short, args.out_conventional, args.out_combined)):
        parser.error("at least one output is required")
    policy = load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)
    result = run_router(args.query, args.db, policy["thresholds"], args.threads,
                        args.out_short, args.out_conventional, args.out_combined, args.recover_short_fragments)
    if args.provenance:
        write_json_atomic(args.provenance, result)


if __name__ == "__main__":
    def terminate(signum, _frame):
        # Unwind TemporaryDirectory and subprocess.run on external termination.
        # SIGKILL cannot be handled by any process.
        print(f"[ERRO] Roteador interrompido por {signal.Signals(signum).name}.", file=sys.stderr)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
