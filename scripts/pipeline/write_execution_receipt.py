#!/usr/bin/env python3
"""Write the public per-sample execution receipt (``execution.json``).

This is the technical/scientific outcome contract for a single sample run:
a small, stable JSON document that downstream consumers (dashboards, batch
summaries, this pipeline's own regression tests) can read without depending
on the internal shape of Evidence V2 or the pipeline log.

Required fields:
  status            "completed" | "failed" — process-level outcome.
  exit_code         int — the pipeline's own exit code for this sample.
  technical_state   "COMPLETED" | "FAILED" — machine-facing terminal state.
  scientific_call   free-form label for the scientific outcome that
                     produced this technical state (e.g.
                     "negative_confirmed_host_saturated"). Optional: a
                     technical failure need not have a scientific call yet.

This module never decides the outcome itself -- it only validates internal
consistency (status/exit_code/technical_state must agree) and writes the
document atomically.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
VALID_STATUS = {"completed", "failed"}
VALID_TECHNICAL_STATE = {"COMPLETED", "FAILED"}


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def build_receipt(
    *,
    sample: str,
    status: str,
    exit_code: int,
    technical_state: str,
    scientific_call: str = "",
    detail: str = "",
) -> dict:
    if status not in VALID_STATUS:
        raise ValueError(f"status invalido: {status!r} — use {sorted(VALID_STATUS)}")
    if technical_state not in VALID_TECHNICAL_STATE:
        raise ValueError(
            f"technical_state invalido: {technical_state!r} — use {sorted(VALID_TECHNICAL_STATE)}"
        )
    if status == "completed" and exit_code != 0:
        raise ValueError("status=completed exige exit_code=0")
    if status == "failed" and exit_code == 0:
        raise ValueError("status=failed exige exit_code diferente de 0")
    if status == "completed" and technical_state != "COMPLETED":
        raise ValueError("status=completed exige technical_state=COMPLETED")
    if status == "failed" and technical_state != "FAILED":
        raise ValueError("status=failed exige technical_state=FAILED")
    root = Path(__file__).resolve().parents[2]
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from genein.identity import software_version, source_commit

    return {
        "schema_version": SCHEMA_VERSION,
        "software_version": software_version(root),
        "source_commit": source_commit(root),
        "sample": sample,
        "status": status,
        "exit_code": exit_code,
        "technical_state": technical_state,
        "scientific_call": scientific_call or None,
        "detail": detail or None,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--technical-state", required=True, choices=sorted(VALID_TECHNICAL_STATE))
    parser.add_argument("--scientific-call", default="")
    parser.add_argument("--detail", default="")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        payload = build_receipt(
            sample=args.sample,
            status=args.status,
            exit_code=args.exit_code,
            technical_state=args.technical_state,
            scientific_call=args.scientific_call,
            detail=args.detail,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return

    _write_json_atomic(args.out, payload)
    print(str(args.out))


if __name__ == "__main__":
    main()
