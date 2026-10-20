#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .common import read_tsv, write_tsv_atomic
    from .evaluate_controls import validate_manifest
except ImportError:
    from common import read_tsv, write_tsv_atomic
    from evaluate_controls import validate_manifest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from input_validation import validate_batch_id, validate_fastq, validate_sample_id


FIELDS = ["batch_id", "sample_id", "role", "library_mode", "umi_mode", "r1", "r2", "expected_target"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly validate and normalize a Gene-In batch manifest")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = read_tsv(args.manifest)
    validate_manifest(rows)
    base = Path(args.manifest).resolve().parent
    normalized = []
    seen_paths = set()
    batch_ids = set()
    for row in rows:
        item = {key: row.get(key, "") for key in FIELDS}
        item["sample_id"] = validate_sample_id(item["sample_id"])
        item["batch_id"] = validate_batch_id(item["batch_id"])
        batch_ids.add(item["batch_id"])
        if item["role"] == "positive" and not item["expected_target"].strip():
            raise ValueError(f"controle positivo sem expected_target: {item['sample_id']}")
        if item["umi_mode"] != "none" and item["library_mode"] == "unknown":
            raise ValueError(f"UMI exige library_mode conhecido: {item['sample_id']}")
        for key in ("r1", "r2"):
            path = Path(item[key])
            path = path if path.is_absolute() else base / path
            if not path.is_file():
                raise ValueError(f"manifest input does not exist: {path}")
            path_key = str(path.resolve()).lower()
            if path_key in seen_paths:
                raise ValueError(f"manifest input reused by another sample: {path}")
            seen_paths.add(path_key)
            item[key] = str(path.resolve())
        validate_fastq(Path(item["r1"]), Path(item["r2"]))
        normalized.append(item)
    if len(batch_ids) != 1:
        raise ValueError("manifest must contain exactly one batch_id")
    if not any(item["role"] == "sample" for item in normalized):
        raise ValueError("manifest must contain at least one analytical sample")
    write_tsv_atomic(args.out, normalized, FIELDS)


if __name__ == "__main__":
    main()
