#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import sys
import tempfile
from pathlib import Path
from collections import defaultdict

try:
    from .common import as_float, iter_tsv, write_tsv_atomic
    from .disk_space import EvidenceDiskError, guard_floor, require_step_space
    from .line_sort import LineSorter, iter_merged
except ImportError:
    from common import as_float, iter_tsv, write_tsv_atomic
    from disk_space import EvidenceDiskError, guard_floor, require_step_space
    from line_sort import LineSorter, iter_merged


FIELDS = [
    "qseqid", "task", "target_sseqid", "target_taxon", "target_bitscore", "target_qcov",
    "competitor_sseqid", "competitor_taxon", "competitor_category", "competitor_bitscore",
    "competitor_qcov", "delta_bitscore", "delta_bitscore_fraction", "qcov_difference_pp",
    "qcov_difference_abs_pp",
    "specificity_status", "specificity_flags", "target_evidence_json",
]


def reference_evidence(hits, min_delta, max_qcov_difference_pp, search_complete):
    """Compare each target reference without lending the best target's status.

    Taxon preference is conditional on the labelled panel, not confirmation
    of a species in the sample. Scores from different BLAST tasks never mix.
    """
    by_subject = {}
    for hit in hits:
        subject = hit["sseqid"]
        previous = by_subject.get(subject)
        if previous is not None and (
            previous.get("category", "UNLABELED"), previous.get("taxon", "")
        ) != (hit.get("category", "UNLABELED"), hit.get("taxon", "")):
            raise ValueError(f"conflicting subject labels: {subject}")
        if previous is None or as_float(hit.get("best_bitscore")) > as_float(previous.get("best_bitscore")):
            by_subject[subject] = hit
    targets = [h for h in by_subject.values() if h.get("category") == "TARGET_VIRUS"]
    other = [h for h in by_subject.values() if h.get("category", "UNLABELED") != "TARGET_VIRUS"]
    output = []
    for target in sorted(targets, key=lambda h: h["sseqid"]):
        # Reuse exactly the category-level policy, for this reference alone.
        group = evaluate([target, *other], min_delta, max_qcov_difference_pp,
                         search_complete, _reference_details=False)[0]
        taxon = str(target.get("taxon") or "").strip()
        alternatives = [h for h in by_subject.values()
                        if h.get("category") in {"TARGET_VIRUS", "NEAR_NON_TARGET_VIRUS"}
                        and str(h.get("taxon") or "").strip() != taxon]
        rival = max(alternatives, key=lambda h: as_float(h.get("best_bitscore")), default=None)
        flags = []
        taxonomic_status = "NOT_EVALUATED"
        if not taxon:
            flags.append("TARGET_TAXON_UNLABELED")
        elif any(not str(h.get("taxon") or "").strip() for h in alternatives):
            flags.append("COMPETING_TAXON_UNLABELED")
        elif group["specificity_status"] == "NON_TARGET_BEST":
            taxonomic_status = "NON_TARGET_BEST"
        elif group["specificity_status"] == "AMBIGUOUS":
            taxonomic_status = "AMBIGUOUS"
        elif group["specificity_status"] != "TARGET_SPECIFIC":
            flags.append("GROUP_SPECIFICITY_NOT_ESTABLISHED")
        elif rival is None:
            flags.append("NO_OTHER_TAXON_IN_REPORTED_HITS")
        else:
            delta = as_float(target.get("best_bitscore")) - as_float(rival.get("best_bitscore"))
            qcov_diff = abs(as_float(target.get("query_coverage")) - as_float(rival.get("query_coverage"))) * 100
            taxonomic_status = (
                "PANEL_TAXON_PREFERRED"
                if delta >= min_delta and qcov_diff <= max_qcov_difference_pp
                else "AMBIGUOUS"
            )
        output.append({
            "reference_id": target["sseqid"], "taxon": taxon,
            "specificity_status": group["specificity_status"],
            "specificity_flags": group["specificity_flags"],
            "taxonomic_status": taxonomic_status,
            "taxonomic_flags": flags,
            "competing_taxon": str(rival.get("taxon") or "") if rival else "",
            "competing_reference_id": rival["sseqid"] if rival else "",
        })
    return output


def evaluate(
    rows: list[dict[str, str]],
    min_delta: float = 10.0,
    max_qcov_difference_pp: float = 5.0,
    search_complete: bool = True,
    *, _reference_details: bool = True,
) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["qseqid"], row.get("task", "blastn"))].append(row)
    output = []
    for (qseqid, task), hits in sorted(grouped.items()):
        targets = [h for h in hits if h.get("category") == "TARGET_VIRUS"]
        competitors = [h for h in hits if h.get("category") not in {"TARGET_VIRUS", "UNLABELED"}]
        unlabeled = [h for h in hits if h.get("category", "UNLABELED") == "UNLABELED"]
        target = max(targets, key=lambda h: as_float(h.get("best_bitscore")), default=None)
        known_competitor = max(
            competitors, key=lambda h: as_float(h.get("best_bitscore")), default=None
        )
        unknown_blocker = max(
            unlabeled, key=lambda h: as_float(h.get("best_bitscore")), default=None
        )
        competitor = known_competitor
        flags = []
        if not search_complete:
            flags.append("SEARCH_SPACE_UNVERIFIED")
        if unknown_blocker is not None:
            flags.append("UNLABELED_HIT_PRESENT")
        if target is None:
            if known_competitor is not None:
                status = "NON_TARGET_BEST"
            else:
                status = "NOT_EVALUATED"
                competitor = unknown_blocker
            target_score = target_qcov = 0.0
        else:
            target_score = as_float(target.get("best_bitscore"))
            target_qcov = as_float(target.get("query_coverage"))
            if target.get("low_complexity_status") == "LOW_COMPLEXITY":
                flags.append("LOW_COMPLEXITY_QUERY")
            if unknown_blocker is not None and (
                known_competitor is None
                or as_float(unknown_blocker.get("best_bitscore"))
                > as_float(known_competitor.get("best_bitscore"))
            ):
                competitor = unknown_blocker
        competitor_score = as_float(competitor.get("best_bitscore")) if competitor else 0.0
        competitor_qcov = as_float(competitor.get("query_coverage")) if competitor else 0.0
        delta = target_score - competitor_score
        fraction = delta / target_score if target_score else 0.0
        # The configured criterion is a maximum absolute difference.  Using
        # only the signed difference would incorrectly accept a competitor
        # covering substantially more of the query than the target.
        qcov_diff_pp = (target_qcov - competitor_qcov) * 100.0
        qcov_difference_abs_pp = abs(qcov_diff_pp)
        if target is not None and known_competitor is None and unknown_blocker is None:
            status = "NOT_EVALUATED"
            flags.append("NO_NON_TARGET_COMPETITOR")
        elif target is not None:
            known_score = (
                as_float(known_competitor.get("best_bitscore"))
                if known_competitor else 0.0
            )
            if known_competitor is not None and known_score > target_score:
                status = "NON_TARGET_BEST"
                competitor = known_competitor
                competitor_score = known_score
                competitor_qcov = as_float(known_competitor.get("query_coverage"))
                delta = target_score - competitor_score
                fraction = delta / target_score if target_score else 0.0
                qcov_diff_pp = (target_qcov - competitor_qcov) * 100.0
                qcov_difference_abs_pp = abs(qcov_diff_pp)
            elif unknown_blocker is not None:
                status = "AMBIGUOUS"
            elif (
                delta >= min_delta
                and qcov_difference_abs_pp <= max_qcov_difference_pp
                and not flags
            ):
                status = "TARGET_SPECIFIC"
            else:
                status = "AMBIGUOUS"
        if not search_complete and status == "TARGET_SPECIFIC":
            status = "NOT_EVALUATED"
        output.append({
            "qseqid": qseqid, "task": task,
            "target_sseqid": target.get("sseqid", "") if target else "",
            "target_taxon": target.get("taxon", "") if target else "",
            "target_bitscore": f"{target_score:.6f}", "target_qcov": f"{target_qcov:.6f}",
            "competitor_sseqid": competitor.get("sseqid", "") if competitor else "",
            "competitor_taxon": competitor.get("taxon", "") if competitor else "",
            "competitor_category": competitor.get("category", "") if competitor else "",
            "competitor_bitscore": f"{competitor_score:.6f}", "competitor_qcov": f"{competitor_qcov:.6f}",
            "delta_bitscore": f"{delta:.6f}", "delta_bitscore_fraction": f"{fraction:.6f}",
            "qcov_difference_pp": f"{qcov_diff_pp:.6f}",
            "qcov_difference_abs_pp": f"{qcov_difference_abs_pp:.6f}",
            "specificity_status": status,
            "specificity_flags": ";".join(flags) or "OK",
            "target_evidence_json": json.dumps(
                reference_evidence(hits, min_delta, max_qcov_difference_pp, search_complete)
                if _reference_details else [],
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ),
        })
    return output


_COMPACT_FIELDS = (
    "qseqid", "task", "sseqid", "category", "taxon",
    "best_bitscore", "query_coverage", "low_complexity_status",
)
_GIB = 1024 ** 3


def competitive_space_estimate(fragment_bytes: int, *, regroup: bool = False) -> tuple[int, int]:
    """Return (temporary bytes, output bytes).

    Fragment rows are already grouped by query. This step keeps one query in
    memory and writes one output row per query and BLAST task. A table that is
    not grouped is sorted as compact rows, about the size of the input.
    """
    temporary = fragment_bytes + _GIB if regroup else _GIB // 2
    return temporary, _GIB


def _compact_line(ordinal: int, row: dict) -> str:
    qseqid = row["qseqid"]
    task = row.get("task", "blastn")
    for field, text in (("qseqid", qseqid), ("task", "" if task is None else str(task))):
        if "\t" in str(text) or "\n" in str(text) or "\r" in str(text):
            raise ValueError(f"competitive field {field} contains a tab or line break")
    payload = {field: row[field] for field in _COMPACT_FIELDS if field in row}
    payload["qseqid"] = qseqid
    payload["task"] = task
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"{ordinal}\t{qseqid}\t{task}\t{blob}\n"


def _compact_key(line: str) -> tuple:
    parts = line.split("\t", 3)
    return (parts[1], parts[2], int(parts[0]))


def _row_from_compact(line: str) -> dict:
    blob = line.rstrip("\n").split("\t", 3)[3]
    return json.loads(blob)


def _emit_query(bucket: list[dict], min_delta, max_qcov_difference_pp, search_complete):
    by_task: dict[str, list] = defaultdict(list)
    for row in bucket:
        by_task[row.get("task", "blastn")].append(row)
    for task in sorted(by_task):
        yield evaluate(by_task[task], min_delta, max_qcov_difference_pp, search_complete)[0]


def _emit_sorted(runs, directory, min_delta, max_qcov_difference_pp, search_complete):
    guard_floor(directory, "comparar os hits do painel")
    bucket: list[dict] = []
    current = None
    for line in iter_merged(runs, _compact_key):
        row = _row_from_compact(line)
        key = (row["qseqid"], row.get("task", "blastn"))
        if current is None:
            current = key
        elif key != current:
            yield from _emit_query(bucket, min_delta, max_qcov_difference_pp, search_complete)
            bucket = []
            current = key
        bucket.append(row)
    if bucket:
        yield from _emit_query(bucket, min_delta, max_qcov_difference_pp, search_complete)


def _queries_are_grouped(path: Path) -> bool:
    """True when each query id is contiguous and query ids are nondecreasing."""
    previous = None
    for row in iter_tsv(path):
        qseqid = row["qseqid"]
        if previous is not None and qseqid < previous:
            return False
        previous = qseqid
    return True


def evaluate_disk(path: str | Path, min_delta: float = 10.0,
                 max_qcov_difference_pp: float = 5.0,
                 search_complete: bool = True,
                 work_dir: str | Path | None = None,
                 output_dir: str | Path | None = None):
    """Evaluate one query at a time when the fragment table is grouped by query."""
    source = Path(path)
    workspace = Path(work_dir) if work_dir is not None else (Path(output_dir) if output_dir is not None else source.parent)
    destination = Path(output_dir) if output_dir is not None else workspace
    fragment_bytes = source.stat().st_size
    temporary, output = competitive_space_estimate(fragment_bytes)
    require_step_space(workspace, destination, temporary, output, "comparar os hits do painel")
    with tempfile.TemporaryDirectory(prefix="genein-competitive-", dir=workspace) as tmp:
        directory = Path(tmp)
        grouped = _queries_are_grouped(source)
        if not grouped:
            extra, _output = competitive_space_estimate(fragment_bytes, regroup=True)
            require_step_space(workspace, destination, extra, output, "comparar os hits do painel")
            sorter = LineSorter(
                directory, "hits", _compact_key,
                lambda: guard_floor(directory, "comparar os hits do painel"),
            )
            for ordinal, row in enumerate(iter_tsv(source)):
                sorter.add(_compact_line(ordinal, row))
            yield from _emit_sorted(
                sorter.finish(), directory, min_delta, max_qcov_difference_pp, search_complete,
            )
            return
        bucket: list[dict] = []
        current: str | None = None
        for row in iter_tsv(source):
            qseqid = row["qseqid"]
            if current is None:
                current = qseqid
            elif qseqid != current:
                yield from _emit_query(bucket, min_delta, max_qcov_difference_pp, search_complete)
                bucket = []
                current = qseqid
            bucket.append(row)
        if bucket:
            yield from _emit_query(bucket, min_delta, max_qcov_difference_pp, search_complete)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare target and non-target hits from the same BLAST task/database")
    parser.add_argument("--fragments", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--minimum-delta-bitscore", type=float, default=10.0)
    parser.add_argument("--maximum-qcov-difference-pp", type=float, default=5.0)
    parser.add_argument("--work-dir", help="Directory for competitive temporary files. Defaults to the output directory.")
    parser.add_argument(
        "--search-complete",
        action="store_true",
        help="confirm that the BLAST report limit covered every subject in the competitive DB",
    )
    args = parser.parse_args()
    out = Path(args.out)
    try:
        write_tsv_atomic(
            out,
            evaluate_disk(
                args.fragments,
                args.minimum_delta_bitscore,
                args.maximum_qcov_difference_pp,
                args.search_complete,
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
            f"[ERRO] Comparação competitiva interrompida por {signal.Signals(signum).name}.",
            file=sys.stderr,
        )
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
