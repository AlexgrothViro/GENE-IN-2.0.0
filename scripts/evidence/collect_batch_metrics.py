#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from pathlib import Path

try:
    from .activation_policy import load_public_activation_policy
    from .common import read_tsv, write_tsv_atomic
    from .evidence_profile import gate_catalog
    from .evidence_contract import validate_document
except ImportError:
    from activation_policy import load_public_activation_policy
    from common import read_tsv, write_tsv_atomic
    from evidence_profile import gate_catalog
    from evidence_contract import validate_document


FIELDS = [
    "batch_id", "sample_id", "target", "expected_target", "rpm_post_qc",
    "rpm_nonhost", "sequence_hashes", "evidence_level", "analysis_outcome",
    "positive_control_qualification",
]


def positive_control_qualification(evidence: dict, policy: dict | None = None) -> str:
    gates = {
        gate.get("gate_id"): gate.get("status")
        for gate in evidence.get("promotion_gates", [])
        if isinstance(gate, dict)
    }
    active_policy = policy or load_public_activation_policy()
    required = {
        gate_id for gate_id, definition in gate_catalog(active_policy).items()
        if definition["required_for_candidate_promotion"]
    }
    return (
        "QUALIFIED"
        if all(gates.get(gate_id) == "PASS" for gate_id in required)
        else "NOT_QUALIFIED"
    )


def fastq_reads(path: Path) -> int | None:
    if not path.is_file():
        return None
    opener = gzip.open if path.suffix == ".gz" else open
    lines = 0
    with opener(path, "rt", encoding="utf-8", errors="strict") as handle:
        for lines, _ in enumerate(handle, 1):
            pass
    if lines % 4:
        raise ValueError(f"FASTQ has an incomplete record: {path}")
    return lines // 4


def nonnegative_number(value: object, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a finite non-negative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{context} must be a finite non-negative number")
    return number


def positive_denominator(value: object, context: str) -> float:
    number = nonnegative_number(value, context)
    if number == 0:
        raise ValueError(f"{context} was measured as zero; RPM is not evaluable")
    return number


def post_qc_reads(root: Path, sample: str) -> float:
    path = root / "results" / "qc" / f"{sample}_fastp.json"
    if not path.is_file():
        raise ValueError(f"post-QC denominator was not measured for sample {sample}")
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        report = json.load(handle)
    value = report.get("summary", {}).get("after_filtering", {}).get("total_reads")
    return positive_denominator(value, f"post-QC denominator for sample {sample}")


def collect(
    manifest_rows: list[dict[str, str]], root: Path, evidence_root: Path,
    run_ids: dict[str, str],
) -> list[dict[str, str]]:
    output = []
    positive_targets: dict[str, set[str]] = {}
    for row in manifest_rows:
        if row.get("role") == "positive" and row.get("expected_target"):
            positive_targets.setdefault(row["batch_id"], set()).add(row["expected_target"])
    for item in manifest_rows:
        sample = item["sample_id"]
        if sample not in run_ids:
            raise ValueError(f"run_id ausente para amostra {sample}")
        evidence_dir = evidence_root / "runs" / run_ids[sample]
        if not (evidence_dir / "SUCCESS.json").is_file():
            raise ValueError(f"execução incompleta para amostra {sample}")
        with (evidence_dir / "sample_evidence.json").open("r", encoding="utf-8") as handle:
            evidence = validate_document(json.load(handle))
        hashes = []
        fragment_path = evidence_dir / "fragment_evidence.tsv"
        if fragment_path.is_file():
            hashes = sorted({
                row["sequence_sha256"] for row in read_tsv(fragment_path)
                if row.get("sequence_sha256")
            })
        templates = nonnegative_number(
            evidence.get("metrics", {}).get("unique_templates"),
            f"unique template count for sample {sample}",
        )
        post_qc = post_qc_reads(root, sample)
        nonhost_path = root / "data" / "host_removed" / f"{sample}_R1.host_removed.fastq.gz"
        nonhost_count = fastq_reads(nonhost_path)
        if nonhost_count is not None:
            nonhost = positive_denominator(
                nonhost_count, f"non-host denominator for sample {sample}",
            )
            rpm_nonhost = templates * 1_000_000 / nonhost
        else:
            rpm_nonhost = None
        rpm_post = templates * 1_000_000 / post_qc
        batch_targets = positive_targets.get(item["batch_id"], set())
        fallback_target = sorted(batch_targets)[0] if len(batch_targets) == 1 else "UNSPECIFIED"
        output.append({
            "batch_id": item["batch_id"], "sample_id": sample,
            "target": item.get("expected_target", "") or fallback_target,
            "expected_target": item.get("expected_target", ""), "rpm_post_qc": f"{rpm_post:.8f}",
            "rpm_nonhost": f"{rpm_nonhost:.8f}" if rpm_nonhost is not None else "NA",
            "sequence_hashes": ";".join(hashes), "evidence_level": evidence["evidence_level"],
            "analysis_outcome": evidence["analysis_outcome"],
            "positive_control_qualification": positive_control_qualification(evidence),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect normalized batch metrics from evidence outputs")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--evidence-root")
    parser.add_argument("--run-map", help="TSV with sample_id and run_id")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.repo_root)
    evidence_root = Path(args.evidence_root) if args.evidence_root else root / "results" / "evidence"
    run_ids = {}
    if args.run_map:
        run_ids = {row["sample_id"]: row["run_id"] for row in read_tsv(args.run_map)}
    manifest_rows = read_tsv(args.manifest)
    output = collect(manifest_rows, root, evidence_root, run_ids)
    write_tsv_atomic(args.out, output, FIELDS)


if __name__ == "__main__":
    main()
