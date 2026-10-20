"""U-50-b3r: loci, HSP evidence and competitive hits stay byte-identical with less disk."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

import aggregate_hsps as agg
from aggregate_hsps import FIELDS as FRAGMENT_FIELDS, iter_blast, write_fragment_evidence
from build_hsp_evidence import FIELDS as HSP_FIELDS, build_hsp_evidence, build_hsp_evidence_disk
from build_loci import FIELDS as LOCUS_FIELDS, _build_group, build_loci, build_loci_disk, parse_intervals
from common import iter_tsv, read_tsv, write_tsv_atomic
from competitive_hits import FIELDS as COMPETITIVE_FIELDS, evaluate, evaluate_disk
from disk_space import EvidenceDiskError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fragment_row(**overrides) -> dict:
    row = {field: "" for field in FRAGMENT_FIELDS}
    row.update({
        "qseqid": "q0", "sseqid": "sT", "task": "blastn", "category": "TARGET_VIRUS",
        "taxon": "Virus T", "segment": "unsegmented", "orientation": "+",
        "qlen": "60", "slen": "1000", "hsp_count": "1",
        "query_intervals": "1-40", "reference_intervals": "100-139",
        "query_covered_bp": "40", "reference_covered_bp": "40", "query_coverage": "0.666667",
        "best_evalue": "1e-20", "best_bitscore": "80.000000", "sum_bitscore": "80.000000",
        "adj_identity": "90.000000", "sequence_sha256": "abc", "low_complexity_status": "ACCEPTABLE",
    })
    row.update(overrides)
    return row


def _write_fragments(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=FRAGMENT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _blast_line(qseqid, sseqid, *, bitscore=80, qstart=1, qend=40, sstart=100, send=139,
                qlen=60, slen=1000, length=40, mismatch=1, nident=39) -> str:
    return "\t".join(map(str, [
        qseqid, sseqid, "97.0", length, mismatch, 0, qstart, qend, sstart, send,
        "1e-20", bitscore, qlen, slen, nident, 0,
    ]))


def legacy_loci(path: Path, gap_bp: int, categories: set[str], directory: Path | None = None):
    """Previous SQLite JSON path, kept only as the equivalence oracle."""
    with tempfile.TemporaryDirectory(prefix="genein-loci-ref-", dir=directory) as tmp:
        db = sqlite3.connect(str(Path(tmp) / "loci.sqlite"))
        try:
            db.execute("CREATE TABLE fragments (id INTEGER PRIMARY KEY, s TEXT, segment TEXT, orientation TEXT, task TEXT, payload TEXT)")
            db.execute("CREATE TABLE intervals (s TEXT, segment TEXT, orientation TEXT, task TEXT, start INTEGER, end INTEGER, fragment_id INTEGER)")
            rows, intervals = [], []
            for row_id, row in enumerate(iter_tsv(path), 1):
                if row.get("category", "UNLABELED") not in categories:
                    continue
                key = (row["sseqid"], row.get("segment", "unsegmented"), row.get("orientation", "+"), row.get("task", "blastn"))
                rows.append((row_id, *key, json.dumps(row, ensure_ascii=False, separators=(",", ":"))))
                for start, end in parse_intervals(row["reference_intervals"]):
                    intervals.append((*key, start, end, row_id))
            db.executemany("INSERT INTO fragments VALUES (?,?,?,?,?,?)", rows)
            db.executemany("INSERT INTO intervals VALUES (?,?,?,?,?,?,?)", intervals)
            db.execute("CREATE INDEX interval_order ON intervals(s,segment,orientation,task,start,end,fragment_id)")
            groups = db.execute(
                "SELECT s,segment,orientation,task FROM fragments GROUP BY s,segment,orientation,task "
                "ORDER BY s,segment,orientation,task"
            ).fetchall()
            for key in groups:
                cursor = db.execute(
                    "SELECT i.start,i.end,i.fragment_id,f.payload FROM intervals i JOIN fragments f "
                    "ON f.id=i.fragment_id WHERE i.s=? AND i.segment=? AND i.orientation=? AND i.task=? "
                    "ORDER BY i.start,i.end,i.fragment_id", key,
                )
                items, cache = [], {}
                for start, end, fragment_id, payload in cursor:
                    row = cache.get(fragment_id)
                    if row is None:
                        row = json.loads(payload)
                        cache[fragment_id] = row
                    items.append((start, end, row))
                yield from _build_group(key, items, gap_bp)
        finally:
            db.close()


def legacy_competitive(path: Path, min_delta=10.0, max_qcov=5.0, search_complete=True,
                       directory: Path | None = None):
    """Previous SQLite JSON path, kept only as the equivalence oracle."""
    from itertools import groupby
    with tempfile.TemporaryDirectory(prefix="genein-competitive-ref-", dir=directory) as tmp:
        db = sqlite3.connect(str(Path(tmp) / "hits.sqlite"))
        try:
            db.execute("CREATE TABLE hits(q TEXT, task TEXT, ordinal INTEGER, payload TEXT)")
            batch = [
                (row["qseqid"], row.get("task", "blastn"), ordinal, json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                for ordinal, row in enumerate(iter_tsv(path))
            ]
            db.executemany("INSERT INTO hits VALUES (?,?,?,?)", batch)
            cursor = db.execute("SELECT q,task,payload FROM hits ORDER BY q,task,ordinal")
            for (_qseqid, _task), group in groupby(cursor, key=lambda item: (item[0], item[1])):
                rows = [json.loads(item[2]) for item in group]
                yield evaluate(rows, min_delta, max_qcov, search_complete)[0]
        finally:
            db.close()


def _noncollapsing_rows(count: int) -> list[dict]:
    """One fragment row per HSP, the shape measured on the real sample."""
    categories = ["TARGET_VIRUS", "HOST", "NEAR_NON_TARGET_VIRUS", "UNLABELED"]
    rows = []
    for index in range(count):
        subject = index % 17
        category = categories[subject % len(categories)]
        start = 100 + (index % 400)
        rows.append(_fragment_row(
            qseqid=f"q{index // 3:07d}",
            sseqid=f"s{subject:02d}",
            task="blastn" if index % 2 == 0 else "blastn-short",
            category=category,
            taxon="" if category == "UNLABELED" else f"Taxon {subject}",
            segment="VP1" if subject % 5 == 0 else "unsegmented",
            orientation="+" if index % 7 else "-",
            reference_intervals=f"{start}-{start + 39}",
            query_intervals=f"{1 + (index % 5)}-{40 + (index % 5)}",
            best_bitscore=f"{50 + (index % 11):.6f}",
            sum_bitscore=f"{50 + (index % 11):.6f}",
            query_coverage=f"{0.5 + (index % 5) * 0.01:.6f}",
            sequence_sha256=f"{index:064x}",
            low_complexity_status="LOW_COMPLEXITY" if index % 29 == 0 else "ACCEPTABLE",
            hsp_count="1",
        ))
    return rows


def test_loci_match_sqlite_oracle_on_noncollapsing_rows(tmp_path):
    rows = _noncollapsing_rows(2400)
    # Two intervals on one row, and a tie on the same start.
    rows[0]["reference_intervals"] = "100-120;400-430"
    path = tmp_path / "fragments.tsv"
    _write_fragments(path, rows)
    expected = tmp_path / "legacy.tsv"
    produced = tmp_path / "new.tsv"
    categories = {"TARGET_VIRUS", "UNLABELED"}
    write_tsv_atomic(expected, legacy_loci(path, 100, categories), LOCUS_FIELDS)
    write_tsv_atomic(produced, build_loci_disk(path, 100, categories, tmp_path, tmp_path), LOCUS_FIELDS)
    assert _sha(expected) == _sha(produced)
    memory = tmp_path / "memory.tsv"
    write_tsv_atomic(memory, build_loci(read_tsv(path), 100, categories), LOCUS_FIELDS)
    assert _sha(memory) == _sha(produced)
    assert not list(tmp_path.glob("genein-loci-*"))


def test_competitive_matches_sqlite_oracle_grouped_unsorted_and_ties(tmp_path):
    rows = _noncollapsing_rows(900)
    # Equal bitscore: the first row in file order wins.
    rows[1]["qseqid"] = rows[0]["qseqid"]
    rows[1]["task"] = rows[0]["task"]
    rows[1]["best_bitscore"] = rows[0]["best_bitscore"]
    rows[1]["sseqid"] = "s-other"
    rows[1]["category"] = "NEAR_NON_TARGET_VIRUS"
    path = tmp_path / "fragments.tsv"
    _write_fragments(path, rows)
    expected = tmp_path / "legacy.tsv"
    produced = tmp_path / "new.tsv"
    write_tsv_atomic(expected, legacy_competitive(path, search_complete=True), COMPETITIVE_FIELDS)
    write_tsv_atomic(produced, evaluate_disk(path, search_complete=True, work_dir=tmp_path, output_dir=tmp_path), COMPETITIVE_FIELDS)
    assert _sha(expected) == _sha(produced)
    shuffled = rows[::-1]
    reverse = tmp_path / "reverse.tsv"
    _write_fragments(reverse, shuffled)
    reverse_out = tmp_path / "reverse-out.tsv"
    write_tsv_atomic(reverse_out, evaluate_disk(reverse, search_complete=True, work_dir=tmp_path, output_dir=tmp_path), COMPETITIVE_FIELDS)
    memory = tmp_path / "memory.tsv"
    write_tsv_atomic(memory, evaluate(read_tsv(reverse), search_complete=True), COMPETITIVE_FIELDS)
    assert _sha(reverse_out) == _sha(memory)
    assert not list(tmp_path.glob("genein-competitive-*"))


def test_hsp_disk_matches_memory_including_duplicates(tmp_path):
    blast = tmp_path / "hits.tsv"
    lines = []
    for index in range(120):
        lines.append(_blast_line(
            f"q{index // 2:04d}", "sT" if index % 3 else "sH",
            sstart=100 + (index % 30), send=139 + (index % 30),
            bitscore=40 + index % 7,
        ))
    lines.append(lines[0])
    lines.append(lines[4])
    blast.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    fragments = []
    seen = set()
    for line in lines:
        cols = line.split("\t")
        key = tuple(cols)
        if key in seen:
            continue
        seen.add(key)
        qseqid, sseqid = cols[0], cols[1]
        sstart, send = cols[8], cols[9]
        fragments.append(_fragment_row(
            qseqid=qseqid, sseqid=sseqid,
            category="TARGET_VIRUS" if sseqid == "sT" else "HOST",
            taxon="Virus T" if sseqid == "sT" else "Host",
            reference_intervals=f"{sstart}-{send}",
            query_intervals=f"{cols[6]}-{cols[7]}",
            best_bitscore=f"{float(cols[11]):.6f}",
        ))
    fragment_path = tmp_path / "fragments.tsv"
    _write_fragments(fragment_path, fragments)
    loci_path = tmp_path / "loci.tsv"
    write_tsv_atomic(loci_path, build_loci_disk(fragment_path, 100, None, tmp_path, tmp_path), LOCUS_FIELDS)
    records = list(iter_blast(blast, "blastn"))
    loci = read_tsv(loci_path)
    expected = tmp_path / "memory.tsv"
    produced = tmp_path / "disk.tsv"
    write_tsv_atomic(expected, build_hsp_evidence(records, loci), HSP_FIELDS)
    write_tsv_atomic(
        produced,
        build_hsp_evidence_disk([("blastn", blast)], loci_path, tmp_path, tmp_path),
        HSP_FIELDS,
    )
    assert _sha(expected) == _sha(produced)
    reasons = [row["rejection_reason"] for row in read_tsv(produced)]
    assert "DUPLICATE_SOURCE_OBSERVATION" in reasons
    assert "OUT_OF_DECLARED_SCOPE" in reasons
    assert not list(tmp_path.glob("genein-hsp-ids-*"))


def test_existing_overlap_fixture_chain_matches_memory(tmp_path):
    fixture = ROOT / "scripts" / "tests" / "evidence" / "fixtures"
    fragments = tmp_path / "fragment_evidence.tsv"
    write_fragment_evidence(
        [("blastn", fixture / "overlapping_hits.tsv")], fragments, {}, {}, work_dir=tmp_path,
    )
    loci = tmp_path / "locus_evidence.tsv"
    write_tsv_atomic(loci, build_loci_disk(fragments, 100, None, tmp_path, tmp_path), LOCUS_FIELDS)
    write_tsv_atomic(tmp_path / "memory-loci.tsv", build_loci(read_tsv(fragments), 100), LOCUS_FIELDS)
    assert _sha(loci) == _sha(tmp_path / "memory-loci.tsv")
    produced = tmp_path / "hsp.tsv"
    write_tsv_atomic(
        produced,
        build_hsp_evidence_disk([("blastn", fixture / "overlapping_hits.tsv")], loci, tmp_path, tmp_path),
        HSP_FIELDS,
    )
    memory = tmp_path / "hsp-memory.tsv"
    write_tsv_atomic(memory, build_hsp_evidence(list(iter_blast(fixture / "overlapping_hits.tsv", "blastn")), read_tsv(loci)), HSP_FIELDS)
    assert _sha(produced) == _sha(memory)


def test_disk_preflight_stops_before_writing(tmp_path, monkeypatch):
    import disk_space
    path = tmp_path / "fragments.tsv"
    _write_fragments(path, [_fragment_row()])
    out = tmp_path / "locus_evidence.tsv"
    monkeypatch.setattr(
        disk_space.shutil, "disk_usage",
        lambda _path: type("Usage", (), {"total": 10, "used": 10, "free": 0})(),
    )
    with pytest.raises(EvidenceDiskError) as caught:
        write_tsv_atomic(out, build_loci_disk(path, 100, None, tmp_path, tmp_path), LOCUS_FIELDS)
    assert "Espaço livre insuficiente" in str(caught.value)
    assert "GiB" in str(caught.value)
    assert not out.exists()
    assert not list(tmp_path.glob("genein-loci-*"))


def _peak_rss_kib(pid: int) -> int:
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return 0
    for line in status.splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1])
    return 0


def run_scale(rows: int = 400_000, blast_lines: int = 400_000) -> dict:
    """Measure peak disk and RSS. Not part of the pytest collection."""
    import subprocess
    import time

    root = Path(tempfile.mkdtemp(prefix="genein-u50-scale-"))
    script = Path(__file__).resolve()

    def measure(phase: str, *extra: str) -> dict:
        work = root / phase
        work.mkdir()
        proc = subprocess.Popen(
            [sys.executable, str(script), phase, str(work), *extra],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        peak_disk = 0
        peak_rss = 0
        while proc.poll() is None:
            peak_rss = max(peak_rss, _peak_rss_kib(proc.pid))
            disk = sum(item.stat().st_size for item in work.rglob("*") if item.is_file())
            peak_disk = max(peak_disk, disk)
            time.sleep(0.05)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode()[-4000:])
        return {
            "returncode": proc.returncode,
            "peak_disk_bytes": peak_disk,
            "peak_rss_kib": peak_rss,
            "stdout": stdout.decode()[-500:],
        }

    summary = {
        "fragment_rows": rows,
        "blast_lines": blast_lines,
        "loci_old": measure("loci-old", str(rows)),
        "loci_new": measure("loci-new", str(rows)),
        "competitive_old": measure("competitive-old", str(rows)),
        "competitive_new": measure("competitive-new", str(rows)),
        "hsp_new": measure("hsp-new", str(blast_lines)),
        "aggregate_new": measure("aggregate-new", str(blast_lines)),
    }
    summary["loci_sha_identical"] = _sha(root / "loci-old" / "loci.tsv") == _sha(root / "loci-new" / "loci.tsv")
    summary["competitive_sha_identical"] = (
        _sha(root / "competitive-old" / "competitive.tsv") == _sha(root / "competitive-new" / "competitive.tsv")
    )
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("root", root)
    return summary


def _phase(phase: str, work: str, count: str) -> None:
    directory = Path(work)
    number = int(count)
    if phase == "loci-old":
        path = directory / "fragments.tsv"
        _write_fragments(path, _noncollapsing_rows(number))
        out = directory / "loci.tsv"
        write_tsv_atomic(out, legacy_loci(path, 100, {"TARGET_VIRUS", "UNLABELED"}, directory), LOCUS_FIELDS)
        return
    if phase == "loci-new":
        path = directory / "fragments.tsv"
        _write_fragments(path, _noncollapsing_rows(number))
        out = directory / "loci.tsv"
        write_tsv_atomic(out, build_loci_disk(path, 100, None, directory, directory), LOCUS_FIELDS)
        return
    if phase == "competitive-old":
        path = directory / "fragments.tsv"
        _write_fragments(path, _noncollapsing_rows(number))
        out = directory / "competitive.tsv"
        write_tsv_atomic(out, legacy_competitive(path, search_complete=True, directory=directory), COMPETITIVE_FIELDS)
        return
    if phase == "competitive-new":
        path = directory / "fragments.tsv"
        _write_fragments(path, _noncollapsing_rows(number))
        out = directory / "competitive.tsv"
        write_tsv_atomic(out, evaluate_disk(path, search_complete=True, work_dir=directory, output_dir=directory), COMPETITIVE_FIELDS)
        return
    if phase == "hsp-new":
        blast = directory / "hits.tsv"
        with blast.open("w", encoding="utf-8", newline="\n") as handle:
            for index in range(number):
                handle.write(_blast_line(
                    f"q{index // 2:07d}", f"s{index % 17:02d}",
                    sstart=100 + (index % 50), send=130 + (index % 50),
                ) + "\n")
                if index % 1000 == 0:
                    handle.write(_blast_line(
                        f"q{index // 2:07d}", f"s{index % 17:02d}",
                        sstart=100 + (index % 50), send=130 + (index % 50),
                    ) + "\n")
        fragments = directory / "fragments.tsv"
        rows = []
        for index in range(number):
            rows.append(_fragment_row(
                qseqid=f"q{index // 2:07d}", sseqid=f"s{index % 17:02d}",
                category="TARGET_VIRUS",
                reference_intervals=f"{100 + (index % 50)}-{130 + (index % 50)}",
            ))
        _write_fragments(fragments, rows)
        loci = directory / "loci.tsv"
        write_tsv_atomic(loci, build_loci_disk(fragments, 100, None, directory, directory), LOCUS_FIELDS)
        out = directory / "hsp.tsv"
        write_tsv_atomic(out, build_hsp_evidence_disk([("blastn", blast)], loci, directory, directory), HSP_FIELDS)
        return
    if phase == "aggregate-new":
        blast = directory / "report.tsv"
        with blast.open("w", encoding="utf-8", newline="\n") as handle:
            for index in range(number):
                # Distinct query/subject/coordinate so aggregation does not collapse.
                start = 10 + (index % 500)
                handle.write(_blast_line(
                    f"q{index:07d}", f"s{index % 23:02d}",
                    qstart=1, qend=20, sstart=start, send=start + 19,
                ) + "\n")
        out = directory / "fragment_evidence.tsv"
        write_fragment_evidence([("blastn", blast)], out, {}, {}, work_dir=directory)
        return
    raise SystemExit(f"unknown phase {phase}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {
        "loci-old", "loci-new", "competitive-old", "competitive-new", "hsp-new", "aggregate-new",
    }:
        _phase(*sys.argv[1:4])
    else:
        run_scale()
