#!/usr/bin/env python3
"""Record the lengths of reads available after QC/host filtering.

This inventory counts reads, not templates or viral evidence. Its count enables
read rescue independently of the lengths of host/background contigs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from input_validation import iter_fastq


def inventory(paths: list[Path]) -> dict:
    inputs = []
    maximum_read_length = 0
    for path in paths:
        counts = {"below_20": 0, "20_34": 0, "35_54": 0,
                  "55_74": 0, "75_100": 0, "above_100": 0}
        for _, sequence in iter_fastq(path):
            length = len(sequence)
            maximum_read_length = max(maximum_read_length, length)
            bucket = ("below_20" if length < 20 else "20_34" if length < 35
                      else "35_54" if length < 55 else "55_74" if length < 75
                      else "75_100" if length <= 100 else "above_100")
            counts[bucket] += 1
        inputs.append({"path": str(path.resolve()), "reads_by_length": counts})
    short_count = sum(sum(item["reads_by_length"][bucket]
                          for bucket in ("20_34", "35_54", "55_74", "75_100"))
                      for item in inputs)
    return {"schema_version": "1.0", "stage": "post_qc_host_filter",
            "unit": "read", "short_read_count": short_count,
            "maximum_read_length_bp": maximum_read_length, "inputs": inputs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fastq", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    temporary = args.out.with_name(args.out.name + f".tmp.{os.getpid()}")
    try:
        result = inventory(args.fastq)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, args.out)
        print(result["short_read_count"])
        return 0
    except (OSError, ValueError, EOFError) as exc:
        print(f"[ERRO] Inventario de reads curtos: {exc}", file=sys.stderr)
        return 1
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
