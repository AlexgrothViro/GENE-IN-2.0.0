#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

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
        )
        result["controls"]["metrics"] = dict(status)
        result["control_metrics"] = dict(status)
        write_json_atomic(json_path, result)
        write_text_atomic(directory / "evidence_report.md", render(result))


if __name__ == "__main__":
    main()
