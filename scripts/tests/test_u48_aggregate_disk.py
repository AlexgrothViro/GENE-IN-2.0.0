"""U-48-b3: aggregated HSP rows stay byte-identical while using less disk."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from itertools import chain, groupby
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

import aggregate_hsps as agg
from aggregate_hsps import (
    AggregationDiskError,
    iter_blast,
    load_labels,
    require_aggregation_space,
    write_fragment_evidence,
)
from common import write_tsv_atomic


def _line(qseqid, sseqid, *, bitscore=20.0, evalue="1e-5", pident="90.0",
          qstart=1, qend=10, sstart=1, send=10, qlen=20, slen=100,
          length=10, mismatch=1, gapopen=0, nident=9, gaps=0):
    return "\t".join(map(str, [
        qseqid, sseqid, pident, length, mismatch, gapopen, qstart, qend,
        sstart, send, evalue, bitscore, qlen, slen, nident, gaps,
    ]))


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def _fasta(path: Path, queries: list[str]) -> None:
    path.write_text("".join(f">{query}\n{'ACGT' * 5}\n" for query in queries), encoding="utf-8")


def _labels(path: Path) -> None:
    path.write_text(
        "sseqid\tcategory\ttaxon\tsegment\n"
        "sA\tTARGET_VIRUS\tVirus A\tVP1\n"
        "sB\tHOST\tHomo sapiens\t\n"
        "sC\tNEAR_NON_TARGET_VIRUS\tVirus C\tVP2\n",
        encoding="utf-8",
    )


def _reference_rows(records, sequences, labels, assembly_method=""):
    """Previous SQLite JSON aggregation, retained only as the equivalence oracle."""
    with tempfile.TemporaryDirectory(prefix="genein-hsps-ref-") as tmp:
        db = sqlite3.connect(str(Path(tmp) / "groups.sqlite"))
        try:
            db.execute("PRAGMA cache_size=-8192")
            db.execute("PRAGMA temp_store=FILE")
            db.execute(
                "CREATE TABLE hits (q TEXT, s TEXT, task TEXT, segment TEXT, "
                "orientation TEXT, ordinal INTEGER, payload TEXT)"
            )

            def rows():
                for ordinal, hit in enumerate(records):
                    orientation = "+" if (hit["qend"] - hit["qstart"]) * (hit["send"] - hit["sstart"]) >= 0 else "-"
                    segment = labels.get(hit["sseqid"], {}).get("segment", "unsegmented") or "unsegmented"
                    yield (
                        hit["qseqid"], hit["sseqid"], hit["task"], segment, orientation,
                        ordinal, json.dumps(hit),
                    )

            db.executemany("INSERT INTO hits VALUES (?,?,?,?,?,?,?)", rows())
            db.commit()
            cursor = db.execute(
                "SELECT q,s,task,segment,orientation,payload FROM hits "
                "ORDER BY q,s,task,segment,orientation,ordinal"
            )
            for _key, group in groupby(cursor, key=lambda row: row[:5]):
                yield from agg.aggregate(
                    [json.loads(row[5]) for row in group], sequences, labels, assembly_method,
                )
        finally:
            db.close()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compare(tmp: Path, specs: list[tuple[str, Path]], fasta: Path | None, labels: Path | None):
    sequences = {}
    if fasta is not None:
        from common import read_fasta
        sequences = read_fasta(fasta)
    label_map = load_labels(str(labels) if labels else None)
    records = list(chain.from_iterable(iter_blast(path, task) for task, path in specs))
    reference = tmp / "reference.tsv"
    produced = tmp / "produced.tsv"
    write_tsv_atomic(reference, _reference_rows(records, sequences, label_map), agg.FIELDS)
    write_fragment_evidence(
        specs, produced, sequences, label_map, work_dir=tmp, 
    )
    assert _sha(reference) == _sha(produced)
    return produced


def test_grouped_queries_ties_profiles_and_absent_query(tmp_path):
    fasta = tmp_path / "queries.fa"
    _fasta(fasta, ["q2", "q10", "qZ"])
    labels = tmp_path / "labels.tsv"
    _labels(labels)
    short = tmp_path / "short.tsv"
    conventional = tmp_path / "conventional.tsv"
    _write(short, [
        _line("q2", "sB", bitscore=3.3, evalue="1e-3"),
        _line("q2", "sB", bitscore=1.1, evalue="1e-3"),
        _line("q2", "sA", bitscore=8, qstart=1, qend=8, sstart=5, send=12, length=8, nident=7),
        _line("q10", "sA", bitscore=4),
        _line("q10", "sC", bitscore=4, qstart=2, qend=9, sstart=2, send=9, length=8, mismatch=0, nident=8),
        _line("q10", "sC", bitscore=4, qstart=2, qend=9, sstart=2, send=9, length=8, mismatch=0, nident=8),
    ])
    _write(conventional, [
        _line("q10", "sA", bitscore=15, evalue="1e-8"),
        _line("q2", "sA", bitscore=1.25, qstart=11, qend=20, sstart=40, send=49),
        _line("q2", "sA", bitscore=9, qstart=1, qend=10, sstart=80, send=89),
    ])
    produced = _compare(tmp_path, [
        ("blastn-short", short),
        ("blastn", conventional),
    ], fasta, labels)
    text = produced.read_text(encoding="utf-8")
    assert "qZ" not in text
    body = [line.split("\t")[0] for line in text.splitlines()[1:]]
    assert body == sorted(body)


def test_interleaved_queries_match_sqlite_order(tmp_path):
    fasta = tmp_path / "queries.fa"
    _fasta(fasta, ["qA", "qB", "qMissing"])
    blast = tmp_path / "interleaved.tsv"
    _write(blast, [
        _line("qB", "sA", bitscore=5),
        _line("qA", "sB", bitscore=6, qstart=1, qend=10, sstart=3, send=12),
        _line("qB", "sA", bitscore=7, qstart=4, qend=12, sstart=4, send=12, length=9, nident=8),
        _line("qA", "sC", bitscore=2),
        _line("qB", "sC", bitscore=2, evalue="0.5"),
    ])
    produced = _compare(tmp_path, [("blastn", blast)], fasta, None)
    assert "qMissing" not in produced.read_text(encoding="utf-8")


def test_same_task_across_files_merges_one_group(tmp_path):
    first = tmp_path / "a.tsv"
    second = tmp_path / "b.tsv"
    _write(first, [_line("q", "sA", bitscore=1.5)])
    _write(second, [_line("q", "sA", bitscore=2.5, qstart=5, qend=14, sstart=5, send=14)])
    produced = _compare(tmp_path, [("blastn", first), ("blastn", second)], None, None)
    rows = produced.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2
    assert rows[1].split("\t")[9] == "2"


def test_spill_path_matches_in_memory_path(tmp_path, monkeypatch):
    blast = tmp_path / "many.tsv"
    lines = []
    for index in range(6):
        lines.append(_line(
            "q", "sA" if index % 2 == 0 else "sB",
            bitscore=10 + index, qstart=1 + index, qend=10 + index,
            sstart=1 + index, send=10 + index,
        ))
    _write(blast, lines)
    monkeypatch.setattr(agg, "QUERY_HITS_IN_RAM", 2)
    _compare(tmp_path, [("blastn-short", blast)], None, None)


def test_existing_overlap_fixture_matches_reference(tmp_path):
    fixture = ROOT / "scripts" / "tests" / "evidence" / "fixtures"
    _compare(
        tmp_path,
        [("blastn", fixture / "overlapping_hits.tsv")],
        fixture / "query_sequences.txt",
        fixture / "subject_labels.tsv",
    )


def test_disk_preflight_stops_before_writing(tmp_path, monkeypatch, capsys):
    blast = tmp_path / "one.tsv"
    _write(blast, [_line("q", "sA")])
    monkeypatch.setattr(
        agg.shutil, "disk_usage",
        lambda path: type("Usage", (), {"total": 10, "used": 10, "free": 0})(),
    )
    out = tmp_path / "fragment_evidence.tsv"
    with pytest.raises(AggregationDiskError) as caught:
        require_aggregation_space(tmp_path, tmp_path, blast.stat().st_size)
    assert "Espaço livre insuficiente" in str(caught.value)
    assert "GiB" in str(caught.value)
    monkeypatch.setattr(sys, "argv", [
        "aggregate_hsps.py", "--blast", f"blastn={blast}",
        "--work-dir", str(tmp_path), "--out", str(out),
    ])
    with pytest.raises(SystemExit) as status:
        agg.main()
    assert status.value.code == 1
    assert "Espaço livre insuficiente" in capsys.readouterr().err
    assert not out.exists()
    assert not list(tmp_path.glob("genein-hsps-*"))


def _synthetic_report(path: Path, queries: int, subjects: int, hits_per_pair: int) -> int:
    """Contiguous queries, several subjects, overlapping HSPs and one exact duplicate."""
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for query_index in range(queries):
            qseqid = f"q{query_index:07d}"
            for subject_index in range(subjects):
                sseqid = f"s{subject_index:03d}"
                for hit_index in range(hits_per_pair):
                    start = 1 + (hit_index % 5)
                    handle.write(_line(
                        qseqid, sseqid, bitscore=10 + hit_index + (subject_index % 3) * 0.1,
                        qstart=start, qend=start + 9, sstart=start, send=start + 9,
                    ) + "\n")
                    count += 1
                    if hit_index == 0:
                        handle.write(_line(
                            qseqid, sseqid, bitscore=10,
                            qstart=start, qend=start + 9, sstart=start, send=start + 9,
                        ) + "\n")
                        count += 1
    return count


def run_scale(line_target: int = 2_000_000) -> dict:
    """Measure peak disk and RSS of the old SQLite path and the streaming path."""
    import subprocess
    import time

    subjects = 10
    hits_per_pair = 20
    queries = max(1, line_target // (subjects * (hits_per_pair + 1)))
    root = Path(tempfile.mkdtemp(prefix="genein-u48-scale-"))
    report_path = root / "report.tsv"
    actual = _synthetic_report(report_path, queries, subjects, hits_per_pair)
    out_old = root / "old.tsv"
    out_new = root / "new.tsv"
    script = Path(__file__).resolve()

    def measure(phase: str, out: Path) -> dict:
        work = root / phase
        work.mkdir()
        proc = subprocess.Popen(
            [sys.executable, str(script), phase, str(report_path), str(out), str(work)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        peak_disk = 0
        peak_rss_kb = 0
        while proc.poll() is None:
            try:
                status = Path(f"/proc/{proc.pid}/status").read_text()
            except OSError:
                status = ""
            for line in status.splitlines():
                if line.startswith("VmHWM:"):
                    peak_rss_kb = max(peak_rss_kb, int(line.split()[1]))
            disk = sum(item.stat().st_size for item in work.rglob("*") if item.is_file())
            peak_disk = max(peak_disk, disk)
            time.sleep(0.2)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode()[-2000:])
        return {
            "phase": phase,
            "returncode": proc.returncode,
            "peak_disk_bytes": peak_disk,
            "peak_rss_kib": peak_rss_kb,
            "output_bytes": out.stat().st_size,
            "stdout": stdout.decode()[-500:],
        }

    old = measure("old", out_old)
    new = measure("new", out_new)
    same = hashlib.sha256(out_old.read_bytes()).hexdigest() == hashlib.sha256(out_new.read_bytes()).hexdigest()
    summary = {
        "lines": actual,
        "queries": queries,
        "input_bytes": report_path.stat().st_size,
        "sha_identical": same,
        "old": old,
        "new": new,
        "root": str(root),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def _phase_entry(phase: str, report: str, out: str, work: str) -> None:
    os.environ["TMPDIR"] = work
    report_path = Path(report)
    out_path = Path(out)
    if phase == "old":
        write_tsv_atomic(
            out_path, _reference_rows(iter_blast(report_path, "blastn"), {}, {}), agg.FIELDS,
        )
        return
    write_fragment_evidence([("blastn", report_path)], out_path, {}, {}, work_dir=Path(work))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"old", "new"}:
        _phase_entry(*sys.argv[1:5])
    else:
        target = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
        run_scale(target)
