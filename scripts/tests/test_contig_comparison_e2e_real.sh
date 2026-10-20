#!/usr/bin/env bash
set -euo pipefail

for command_name in python3 blastn blastdbcmd makeblastdb bowtie2-build; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "[SKIP] $command_name indisponivel" >&2
    exit 77
  }
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
WORK="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-comparison-e2e.XXXXXX")"
cleanup() {
  local cleanup_status=$?
  if [[ $cleanup_status -ne 0 || -n "${GENEIN_TEST_ARTIFACT_ROOT:-}" ]]; then
    echo "[ARTIFACTS] $WORK (exit=$cleanup_status)" >&2
  else
    rm -rf -- "$WORK"
  fi
}
trap cleanup EXIT

RUN_ID="source-run-0001"
PANEL_ID="panel-real-0001"
COMPARISON_ID="comparison-real-0001"
mkdir -p "$WORK/results/runs/$RUN_ID" "$WORK/panel-sources"
printf '>contig-a\nGATCTAGCGTACCGATGCTAGTCCGATCGTACGATGGCATTCGAGTACCGTATGCA\n' > "$WORK/results/runs/$RUN_ID/assembly_contigs.fa"
printf '>ref-a\nTTTTGATCTAGCGTACCGATGCTAGTCCGATCGTACGATGGCATTCGAGTACCGTATGCAAAAA\n' > "$WORK/panel-sources/target.fa"
printf '>near-a\nCCCCAACCGGTTAACCGGTTAACCGGTTCCCC\n' > "$WORK/panel-sources/near.fa"
printf '>host-a\nAAAATTTTGGGGCCCCAAAATTTTGGGGCCCC\n' > "$WORK/panel-sources/host.fa"
printf '>adapter-a\nAGATCGGAAGAGCACACGTCTGAACTCCAGTCAC\n' > "$WORK/panel-sources/adapter.fa"
printf '>contaminant-a\nGCGCGCATATATGCGCGCATATATGCGCGC\n' > "$WORK/panel-sources/contaminant.fa"
printf '>synthetic-a\nACACACGTGTGTACACACGTGTGTACACAC\n' > "$WORK/panel-sources/synthetic.fa"

bash "$REPO_ROOT/scripts/evidence/build_competitive_db.sh" \
  --out-root "$WORK/results/evidence" --panel-id "$PANEL_ID" \
  --source "TARGET_VIRUS=$WORK/panel-sources/target.fa" \
  --source "NEAR_NON_TARGET_VIRUS=$WORK/panel-sources/near.fa" \
  --source "HOST=$WORK/panel-sources/host.fa" \
  --source "VECTOR_ADAPTER=$WORK/panel-sources/adapter.fa" \
  --source "KNOWN_CONTAMINANT=$WORK/panel-sources/contaminant.fa" \
  --source "SYNTHETIC_SEQUENCE=$WORK/panel-sources/synthetic.fa" >/dev/null

python3 - "$WORK" "$RUN_ID" "$PANEL_ID" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
run_id, panel_id = sys.argv[2:]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

run = root / "results/runs" / run_id
fasta = run / "assembly_contigs.fa"
metadata = run / "metadata.json"
metadata.write_text(json.dumps({"run_id": run_id, "sample": "sample-a", "status": "done"}), encoding="utf-8")
manifest = {
    "schema_version": "1.0", "run_id": run_id, "sample": "sample-a",
    "artifacts": {
        "metadata.json": {"size": metadata.stat().st_size, "sha256": digest(metadata)},
        "assembly_contigs.fa": {"size": fasta.stat().st_size, "sha256": digest(fasta)},
    },
}
(run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
(run / "SUCCESS.json").write_text(json.dumps({
    "schema_version": "1.0", "id": run_id, "status": "done", "manifest": "manifest.json",
    "manifest_sha256": digest(run / "manifest.json"),
}), encoding="utf-8")
PY

bash "$REPO_ROOT/scripts/experimental/contig_comparison/run.sh" \
  --repo-root "$WORK" --comparison-id "$COMPARISON_ID" --sample sample-a \
  --source-type run --source-id "$RUN_ID" --reference-kind panel --database "$PANEL_ID" \
  --blast-task blastn --word-size 11 --evalue 1e-5 --max-target-seqs 50 --threads 1

python3 - "$WORK/results/contig_comparisons/$COMPARISON_ID" <<'PY'
import csv
import json
import sys
from pathlib import Path

result = Path(sys.argv[1])
success = json.loads((result / "SUCCESS.json").read_text(encoding="utf-8"))
manifest = json.loads((result / "comparison_manifest.json").read_text(encoding="utf-8"))
assert success["status"] == "done"
assert manifest["reference_kind"] == "competitive_panel"
assert manifest["contigs_source_run"] == "source-run-0001"
with (result / "hits.tsv").open(encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
assert rows and rows[0]["qseqid"] == "contig-a"
assert not (result.parent / ".staging" / result.name / "SUCCESS.json").exists()
PY

echo "[OK] comparacao real de contigs promovida com SUCCESS.json"
