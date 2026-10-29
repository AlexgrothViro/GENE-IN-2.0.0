#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

try:
    from .activation_policy import load_public_activation_policy
    from .classify_sample import classify
    from .common import read_tsv, write_json_atomic, write_text_atomic
    from .export_evidence import render
except ImportError:
    from activation_policy import load_public_activation_policy
    from classify_sample import classify
    from common import read_tsv, write_json_atomic, write_text_atomic
    from export_evidence import render


def refresh_sample_reports(sample_id: str, control_status: str, evidence_level: str) -> None:
    """Rewrite the sample summary so it carries the same label as sample_evidence.json."""
    work = os.environ.get("GENEIN_WORK_ROOT", "")
    if not work:
        return
    root = Path(work)
    contigs = root / "data/assemblies" / f"{sample_id}_assembly" / "contigs.fa"
    blast = root / "results/blast" / f"{sample_id}_vs_db.tsv"
    report = root / "results/reports" / f"{sample_id}_summary.md"
    if not contigs.is_file() or not blast.is_file():
        return
    script = Path(__file__).resolve().parents[1] / "pipeline" / "report_minimal.sh"
    command = [
        "bash", str(script),
        "--sample", sample_id,
        "--contigs", str(contigs),
        "--blast", str(blast),
        "--out", str(report),
        "--control-status", control_status,
    ]
    if evidence_level:
        command += ["--evidence-level", evidence_level]
    profile = root / "results/blast" / f"{sample_id}_search_profile.json"
    if profile.is_file():
        command += ["--search-profile", str(profile)]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"não foi possível atualizar o resumo de {sample_id} para o estado {control_status}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute evidence after independent batch-control evaluation")
    parser.add_argument("--statuses", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--activation-policy")
    parser.add_argument("--profiles")
    args = parser.parse_args()
    root = Path(args.evidence_root)
    policy = load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)
    statuses: dict[str, dict[str, str]] = {}
    for row in read_tsv(args.statuses):
        sample_id = row["sample_id"]
        if sample_id in statuses:
            raise ValueError(f"ambiguous multiple control statuses for sample {sample_id}")
        statuses[sample_id] = row

    for sample_id, status in statuses.items():
        directory = root / "samples" / sample_id if (root / "samples").is_dir() else root / sample_id
        json_path = directory / "sample_evidence.json"
        with json_path.open("r", encoding="utf-8", errors="strict") as handle:
            previous = json.load(handle)
        fragments_path = directory / "fragment_evidence.tsv"
        result = classify(
            sample_id,
            read_tsv(directory / "locus_evidence.tsv"),
            read_tsv(directory / "competitive_hits.tsv"),
            read_tsv(directory / "read_support.tsv"),
            read_tsv(directory / "coverage.tsv"),
            status["control_status"],
            previous.get("library_mode", "unknown"),
            policy["shadow_mode"],
            previous.get("provenance", {}),
            previous.get("run_id"),
            policy,
            fragments=read_tsv(fragments_path) if fragments_path.is_file() and fragments_path.stat().st_size else None,
        )
        result["controls"]["metrics"] = dict(status)
        result["control_metrics"] = dict(status)
        write_json_atomic(json_path, result)
        write_text_atomic(directory / "evidence_report.md", render(result))
        refresh_sample_reports(sample_id, status["control_status"], result.get("evidence_level", ""))


if __name__ == "__main__":
    main()
