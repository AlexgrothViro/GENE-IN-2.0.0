#!/usr/bin/env bash
# E2E real: BLAST -> Evidence V2 (sidecars) -> Mapper CLI (GI-EG002).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_BIN="${GENE_IN_ENV_BIN:-${GENEIN_BUNDLE_DIR:-$HOME/.gene-in-bundle}/env/bin}"
export PATH="$ENV_BIN:$PATH"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
LOG_ROOT="${GI_EG002_LOG_ROOT:-${GENEIN_TEST_ARTIFACT_ROOT:-${TMPDIR:-/tmp}}/blast-mapper-e2e-$(date +%s)-$$}"
mkdir -p "$LOG_ROOT"
mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
WORK="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-gi-eg002-e2e.XXXXXX")"
echo "E2E_WORK=$WORK"
echo "E2E_LOG=$LOG_ROOT"
QUERY_SEQUENCE="ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGTGCATG"
HOST_SEQUENCE="ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGAAAAAA"
printf '>query_b4\n%s\n' "$QUERY_SEQUENCE" > "$WORK/query.fa"
printf '>target_ref\n%sTGCATCGATCGT\n>host_ref\n%sTGCATCGATCGT\n' \
  "$QUERY_SEQUENCE" "$HOST_SEQUENCE" > "$WORK/panel.fa"
printf 'sseqid\tcategory\ttaxon\tsegment\n' > "$WORK/labels.tsv"
printf 'target_ref\tTARGET_VIRUS\tsynthetic_target\tunsegmented\n' >> "$WORK/labels.tsv"
printf 'host_ref\tHOST\tsynthetic_host\tunsegmented\n' >> "$WORK/labels.tsv"
makeblastdb -in "$WORK/panel.fa" -dbtype nucl -parse_seqids -out "$WORK/panel" >/dev/null
python3 "$ROOT/scripts/tests/write_blast_fixture_manifest.py" "$WORK/panel"

for RUN_ID in b4-eg002-run1 b4-eg002-run2; do
  bash "$ROOT/scripts/evidence/run.sh" \
    --sample b4synthetic \
    --queries "$WORK/query.fa" \
    --profiles "$ROOT/config/evidence_profiles.json" \
    --evidence-root "$WORK/evidence" \
    --run-id "$RUN_ID" \
    --composite-db "$WORK/panel" \
    --subject-labels "$WORK/labels.tsv" \
    --threads 1 \
    --assembly-method velvet >/dev/null
done

FINAL1="$WORK/evidence/runs/b4-eg002-run1"
FINAL2="$WORK/evidence/runs/b4-eg002-run2"
python3 - "$FINAL1" "$FINAL2" <<'PY'
import csv
import json
import sys
from pathlib import Path

r1, r2 = Path(sys.argv[1]), Path(sys.argv[2])
for root in (r1, r2):
    success = json.loads((root / "SUCCESS.json").read_text(encoding="utf-8"))
    assert success.get("mapper_source_version") == "0.2.2", success
    with (root / "hsp_evidence.tsv").open(encoding="utf-8", newline="") as handle:
        hsp = list(csv.DictReader(handle, delimiter="\t"))
    with (root / "locus_evidence.tsv").open(encoding="utf-8", newline="") as handle:
        loci = list(csv.DictReader(handle, delimiter="\t"))
    with (root / "fragment_evidence.tsv").open(encoding="utf-8", newline="") as handle:
        frags = list(csv.DictReader(handle, delimiter="\t"))
    with (root / "template_lineage.tsv").open(encoding="utf-8", newline="") as handle:
        lineage = list(csv.DictReader(handle, delimiter="\t"))
    assert hsp, "hsp_evidence empty"
    assert (root / "template_lineage.tsv").is_file()
    assert all(row.get("coord_system") == "1-based-inclusive" for row in loci)
    assert all(row.get("assembly_method") == "velvet" for row in frags)
    eligible = [h for h in hsp if h["eligible"] == "true"]
    assert eligible and all(h["locus_id"] for h in eligible)
    for h in eligible:
        assert sum(1 for loc in loci if loc["locus_id"] == h["locus_id"]) == 1
    locus_hsp_sum = sum(int(loc["hsp_count"]) for loc in loci)
    assert len(eligible) == locus_hsp_sum, (len(eligible), locus_hsp_sum)
    assert all(
        h["rejection_reason"] != "DUPLICATE_SOURCE_OBSERVATION" or h["eligible"] == "false"
        for h in hsp
    )
    evidence = json.loads((root / "sample_evidence.json").read_text(encoding="utf-8"))
    print(
        f"{root.name}: hsp={len(hsp)} eligible={len(eligible)} "
        f"lineage_rows={len(lineage)} outcome={evidence['analysis_outcome']}"
    )

e1 = json.loads((r1 / "sample_evidence.json").read_text(encoding="utf-8"))
e2 = json.loads((r2 / "sample_evidence.json").read_text(encoding="utf-8"))
for key in ("execution_status", "analysis_outcome", "evidence_level", "reported_conclusion"):
    assert e1[key] == e2[key], (key, e1[key], e2[key])
c1, c2 = e1["candidates"][0], e2["candidates"][0]
assert c1["candidate_class"] == c2["candidate_class"]
assert c1["promotion_status"] == c2["promotion_status"]
assert set(c1["blocking_reasons"]) == set(c2["blocking_reasons"])
gate1 = {(g["gate_id"], g["status"]) for g in c1.get("promotion_gates", c1.get("gates", []))}
gate2 = {(g["gate_id"], g["status"]) for g in c2.get("promotion_gates", c2.get("gates", []))}
if gate1 or gate2:
    assert gate1 == gate2
print("PASS: dual B4 decision identity + hsp/locus invariants")
PY

GRAPH_OUT="$WORK/graph"
mkdir -p "$GRAPH_OUT"
python3 -m genein graph build --run-dir "$FINAL1" --output-root "$GRAPH_OUT" | tee "$WORK/mapper_summary.json"
python3 - "$GRAPH_OUT" "$FINAL1" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

graph_root = Path(sys.argv[1])
run_dir = Path(sys.argv[2])
successes = list(graph_root.rglob("SUCCESS.json"))
assert successes, "mapper SUCCESS missing"
graph_dir = successes[0].parent
success = json.loads(successes[0].read_text(encoding="utf-8"))
assert success.get("mapper_version") == "0.2.2" or success.get("status")
for name in ("hsp_evidence.tsv", "template_lineage.tsv"):
    src = (run_dir / name).read_bytes()
    dst = (graph_dir / name).read_bytes()
    assert hashlib.sha256(src).digest() == hashlib.sha256(dst).digest(), name
print(f"PASS: mapper package at {graph_dir}")
PY

# Persist E2E outputs for review (not only /tmp).
rm -rf "$LOG_ROOT/b4-eg002-run1" "$LOG_ROOT/b4-eg002-run2" "$LOG_ROOT/graph"
cp -a "$FINAL1" "$LOG_ROOT/b4-eg002-run1"
cp -a "$FINAL2" "$LOG_ROOT/b4-eg002-run2"
cp -a "$GRAPH_OUT" "$LOG_ROOT/graph"
python3 "$ROOT/scripts/tests/evidence/compare_b4_decision.py" "$WORK/evidence/runs" \
  | tee "$LOG_ROOT/decision_comparison.txt"

python3 - <<'PY'
import shutil
import subprocess
import sys
from importlib.metadata import version

print("python", sys.version.split()[0])
for cmd in ("blastn", "bowtie2", "samtools", "umi_tools"):
    path = shutil.which(cmd)
    print(cmd, path or "MISSING")
    if not path:
        continue
    try:
        flag = "-version" if cmd == "blastn" else "--version"
        out = subprocess.check_output([cmd, flag], text=True, stderr=subprocess.STDOUT)
    except Exception as exc:  # noqa: BLE001
        out = str(exc)
    print(" ", out.strip().splitlines()[0][:160])
try:
    print("jsonschema", version("jsonschema"))
    print("pytest", version("pytest"))
except Exception as exc:  # noqa: BLE001
    print("package versions unavailable:", exc)
PY

echo "DONE_WORK=$WORK"
echo "DONE_LOG=$LOG_ROOT"
