#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from collections import defaultdict

try:
    from .common import read_tsv, write_tsv_atomic
except ImportError:
    from common import read_tsv, write_tsv_atomic


ROLES = {"sample", "negative_extraction", "negative_library", "negative_sequencing", "positive"}
LIBRARY_MODES = {"shotgun", "amplicon", "targeted", "unknown"}
UMI_MODES = {"none", "read_name", "tag"}
FIELDS = [
    "batch_id", "sample_id", "target", "control_status", "normalization",
    "sample_rpm", "maximum_negative_rpm", "sample_to_negative_ratio", "shared_sequence",
    "index_hopping", "donor_sample_id", "donor_to_receiver_ratio",
]


def validate_manifest(rows: list[dict[str, str]]) -> None:
    required = {"batch_id", "sample_id", "role", "library_mode", "umi_mode", "r1", "r2", "expected_target"}
    if not rows:
        raise ValueError("batch manifest is empty")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"batch manifest missing columns: {', '.join(sorted(missing))}")
    seen = set()
    for row in rows:
        if row["role"] not in ROLES:
            raise ValueError(f"invalid role: {row['role']}")
        if row["library_mode"] not in LIBRARY_MODES:
            raise ValueError(f"invalid library_mode: {row['library_mode']}")
        if row["umi_mode"] not in UMI_MODES:
            raise ValueError(f"invalid umi_mode: {row['umi_mode']}")
        key = (row["batch_id"], row["sample_id"])
        if key in seen:
            raise ValueError(f"duplicate sample in batch: {key}")
        seen.add(key)


def measured_metric(row: dict[str, str], field: str) -> float:
    value = row.get(field)
    if value in {None, "", "NA"}:
        raise ValueError(
            f"metric {field} is not measured for sample {row.get('sample_id', '')}"
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"metric {field} is invalid for sample {row.get('sample_id', '')}"
        ) from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(
            f"metric {field} is invalid for sample {row.get('sample_id', '')}"
        )
    return number


def evaluate(manifest: list[dict[str, str]], metrics: list[dict[str, str]], ratio_threshold: float = 10.0) -> list[dict]:
    validate_manifest(manifest)
    manifest_by_sample = {(r["batch_id"], r["sample_id"]): r for r in manifest}
    metrics_by_batch_target = defaultdict(list)
    all_enriched = []
    seen_metrics = set()
    for metric in metrics:
        key = (metric["batch_id"], metric["sample_id"])
        if key not in manifest_by_sample:
            raise ValueError(f"metrics reference unknown sample: {key}")
        if key in seen_metrics:
            raise ValueError(f"duplicate metrics for sample: {key}")
        seen_metrics.add(key)
        enriched = dict(metric)
        enriched.update({"role": manifest_by_sample[key]["role"]})
        all_enriched.append(enriched)
        metrics_by_batch_target[(metric["batch_id"], metric.get("target", ""))].append(enriched)
    missing_metrics = sorted(set(manifest_by_sample) - seen_metrics)
    if missing_metrics:
        raise ValueError(f"metrics missing for samples: {missing_metrics}")

    output = []
    positives_by_batch = defaultdict(list)
    for row in all_enriched:
        if row["role"] == "positive":
            positives_by_batch[row["batch_id"]].append(row)
    for (batch_id, target), group in sorted(metrics_by_batch_target.items()):
        negatives = [r for r in group if r["role"].startswith("negative_")]
        batch_positives = positives_by_batch[batch_id]
        batch_positive_failure = len(batch_positives) > 1 and all(
            row.get("positive_control_qualification") != "QUALIFIED"
            for row in batch_positives
        )
        positive_failed = any(
            r["role"] == "positive"
            and r.get("expected_target", target) in {"", target}
            and r.get("positive_control_qualification") != "QUALIFIED"
            for r in group
        )
        for sample in (r for r in group if r["role"] == "sample"):
            normalization = "rpm_nonhost" if sample.get("rpm_nonhost", "") not in {"", "NA"} else "rpm_post_qc"
            sample_rpm = measured_metric(sample, normalization)
            negative_values = [measured_metric(row, normalization) for row in negatives]
            max_negative = max(negative_values, default=0.0)
            sample_hashes = set(filter(None, sample.get("sequence_hashes", "").split(";")))
            negative_hashes = set()
            for negative in negatives:
                negative_hashes.update(filter(None, negative.get("sequence_hashes", "").split(";")))
            shared = bool(sample_hashes & negative_hashes)
            donor_id = ""
            donor_ratio = 0.0
            # Donors are intentionally evaluated only within this
            # (batch_id, target) group. Cross-target index hopping is outside
            # the available target-scoped sequence comparison.
            for possible_donor in group:
                if possible_donor["sample_id"] == sample["sample_id"]:
                    continue
                donor_hashes = set(filter(None, possible_donor.get("sequence_hashes", "").split(";")))
                donor_rpm = measured_metric(possible_donor, normalization)
                ratio = donor_rpm / sample_rpm if sample_rpm > 0 else 0.0
                if sample_hashes & donor_hashes and ratio >= ratio_threshold and ratio > donor_ratio:
                    donor_id, donor_ratio = possible_donor["sample_id"], ratio
            index_hopping = bool(donor_id)
            if batch_positive_failure:
                status = "BATCH_GLOBAL_FAILURE"
            elif positive_failed:
                status = "TARGET_CONTROL_FAILURE"
            elif index_hopping:
                status = "INDEX_HOPPING_SUSPECTED"
            elif not negatives:
                status = "UNCONTROLLED"
            elif max_negative <= 0:
                status = "CONTROL_NOT_DETECTED"
            elif max_negative >= sample_rpm:
                status = "CONTROL_EQUAL_OR_HIGHER"
            elif sample_rpm / max_negative >= ratio_threshold and not shared:
                status = "CONTROL_BELOW_SAMPLE"
            else:
                status = "CONTROL_ASSOCIATED_SIGNAL"
            output.append({
                "batch_id": batch_id, "sample_id": sample["sample_id"], "target": target,
                "control_status": status, "normalization": normalization,
                "sample_rpm": f"{sample_rpm:.8f}", "maximum_negative_rpm": f"{max_negative:.8f}",
                "sample_to_negative_ratio": f"{sample_rpm / max_negative:.8f}" if max_negative else "",
                "shared_sequence": "TRUE" if shared else "FALSE",
                "index_hopping": "TRUE" if index_hopping else "FALSE",
                "donor_sample_id": donor_id,
                "donor_to_receiver_ratio": f"{donor_ratio:.8f}" if donor_id else "",
            })
    for control in (row for row in all_enriched if row["role"] != "sample"):
        normalization = "rpm_nonhost" if control.get("rpm_nonhost", "") not in {"", "NA"} else "rpm_post_qc"
        control_rpm = measured_metric(control, normalization)
        output.append({
            "batch_id": control["batch_id"], "sample_id": control["sample_id"],
            "target": control.get("target", ""), "control_status": "CONTROL_NOT_APPLICABLE",
            "normalization": normalization, "sample_rpm": f"{control_rpm:.8f}",
            "maximum_negative_rpm": "", "sample_to_negative_ratio": "", "shared_sequence": "FALSE",
            "index_hopping": "FALSE", "donor_sample_id": "", "donor_to_receiver_ratio": "",
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate batch controls without converting provisional ratios into diagnoses")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sample-metrics", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--provisional-ratio", type=float, default=10.0)
    args = parser.parse_args()
    rows = evaluate(read_tsv(args.manifest), read_tsv(args.sample_metrics), args.provisional_ratio)
    write_tsv_atomic(args.out, rows, FIELDS)


if __name__ == "__main__":
    main()
