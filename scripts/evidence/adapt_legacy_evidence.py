#!/usr/bin/env python3
from __future__ import annotations

import argparse

try:
    from .common import read_tsv, sha256_file, write_json_atomic
    from .evidence_contract import adapt_legacy_document
except ImportError:
    from common import read_tsv, sha256_file, write_json_atomic
    from evidence_contract import adapt_legacy_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicitly adapt legacy hit labels with an auditable migration id")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--labeled", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--adaptation-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = read_tsv(args.labeled)
    labels = sorted(row["evidence_class"] for row in rows if row.get("evidence_class"))
    value = {
        "sample_id": args.sample, "run_id": args.run_id,
        "evidence_class": labels[0] if labels else "NONE",
        "legacy_labels": sorted(set(labels)),
        "provenance": {
            "adapter": "legacy-1.1-read-only",
            "source": args.labeled,
            "source_artifact_sha256": sha256_file(args.labeled),
        },
    }
    write_json_atomic(args.out, adapt_legacy_document(value, adaptation_id=args.adaptation_id))


if __name__ == "__main__":
    main()
