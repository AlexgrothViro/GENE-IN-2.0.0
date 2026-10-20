#!/usr/bin/env python3
"""Compare decisional fields for GI-EG002 B4 handoff (local logs + latest E2E)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def decide(doc: dict) -> dict:
    candidate = doc["candidates"][0]
    gates = {(g.get("gate_id"), g.get("status")) for g in candidate.get("promotion_gates", [])}
    return {
        "execution_status": doc.get("execution_status"),
        "analysis_outcome": doc.get("analysis_outcome"),
        "evidence_level": doc.get("evidence_level"),
        "reported_conclusion": doc.get("reported_conclusion"),
        "candidate_class": candidate.get("candidate_class"),
        "promotion_status": candidate.get("promotion_status"),
        "blocking_reasons": sorted(candidate.get("blocking_reasons") or []),
        "gates": sorted(gates),
    }


def main() -> int:
    hist1 = ROOT / "logs/etapa3/gi-c002-dual/run1/evidence/runs/b4-etapa3-run1/sample_evidence.json"
    hist2 = ROOT / "logs/etapa3/gi-c002-dual/run2/evidence/runs/b4-etapa3-run2/sample_evidence.json"
    new_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/genein-gi-eg002-e2e.PyC5Cs/evidence/runs")
    new1 = new_root / "b4-eg002-run1/sample_evidence.json"
    new2 = new_root / "b4-eg002-run2/sample_evidence.json"
    data = {}
    for name, path in (("hist1", hist1), ("hist2", hist2), ("new1", new1), ("new2", new2)):
        if not path.is_file():
            print(f"MISSING {name} {path}")
            continue
        data[name] = decide(json.loads(path.read_text(encoding="utf-8")))
        print(name, json.dumps(data[name], ensure_ascii=False))
    if "hist1" in data and "hist2" in data:
        print("hist_identical", data["hist1"] == data["hist2"])
    if "new1" in data and "new2" in data:
        print("new_identical", data["new1"] == data["new2"])
    if "hist1" in data and "new1" in data:
        diff = {
            key: (data["hist1"][key], data["new1"][key])
            for key in data["hist1"]
            if data["hist1"][key] != data["new1"][key]
        }
        print("hist_vs_new_diff", json.dumps(diff, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
