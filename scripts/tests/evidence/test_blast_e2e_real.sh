#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
for command_name in python3 blastn blastdbcmd makeblastdb; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "SKIP: $command_name is not installed"
    exit 77
  }
done

mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
WORK="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-b4-e2e.XXXXXX")"
cleanup() {
  local status=$?
  if [[ "$status" -ne 0 || -n "${GENEIN_TEST_ARTIFACT_ROOT:-}" ]]; then
    echo "[ARTIFACTS] $WORK (exit=$status)" >&2
    return
  fi
  case "$WORK" in
    /tmp/genein-b4-e2e.*) rm -rf -- "$WORK" ;;
    *) echo "Refusing to remove unexpected test path: $WORK" >&2 ;;
  esac
}
trap cleanup EXIT

QUERY_SEQUENCE="ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGTGCATG"
HOST_SEQUENCE="ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGAAAAAA"
printf '>query_b4\n%s\n' "$QUERY_SEQUENCE" > "$WORK/query.fa"
printf '>target_ref\n%sTGCATCGATCGT\n>host_ref\n%sTGCATCGATCGT\n' \
  "$QUERY_SEQUENCE" "$HOST_SEQUENCE" > "$WORK/panel.fa"
printf 'sseqid\tcategory\ttaxon\tsegment\n' > "$WORK/labels.tsv"
printf 'target_ref\tTARGET_VIRUS\tsynthetic_target\tunsegmented\n' >> "$WORK/labels.tsv"
printf 'host_ref\tHOST\tsynthetic_host\tunsegmented\n' >> "$WORK/labels.tsv"

makeblastdb -in "$WORK/panel.fa" -dbtype nucl -parse_seqids \
  -out "$WORK/panel" >/dev/null
python3 "$ROOT/scripts/tests/write_blast_fixture_manifest.py" "$WORK/panel"

bash "$ROOT/scripts/evidence/run.sh" \
  --sample b4synthetic \
  --queries "$WORK/query.fa" \
  --profiles "$ROOT/config/evidence_profiles.json" \
  --evidence-root "$WORK/evidence" \
  --run-id b4-test-run-0001 \
  --composite-db "$WORK/panel" \
  --subject-labels "$WORK/labels.tsv" \
  --threads 1 >/dev/null

FINAL="$WORK/evidence/runs/b4-test-run-0001"
python3 - "$FINAL" <<'PY'
import csv
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
if not (root / "SUCCESS.json").is_file():
    raise SystemExit("SUCCESS.json was not promoted")
with (root / "provenance.json").open(encoding="utf-8") as handle:
    provenance = json.load(handle)
with (root / "sample_evidence.json").open(encoding="utf-8") as handle:
    evidence = json.load(handle)
with (root / "competitive_hits.tsv").open(encoding="utf-8", newline="") as handle:
    competitive = list(csv.DictReader(handle, delimiter="\t"))
for name in ("blastn-short.tsv", "blastn.tsv"):
    if not (root / name).is_file():
        raise SystemExit(f"generated BLAST artifact was not preserved: {name}")
blast_paths = {
    record["path"] for key, record in provenance["artifacts"].items()
    if key.startswith("blast_")
}
if blast_paths != {"blastn-short.tsv", "blastn.tsv"}:
    raise SystemExit("generated BLAST provenance is not run-relative and durable")
if provenance["parameters"]["blast_search_complete"] != "true":
    raise SystemExit("BLAST search was not recorded as complete")
if provenance["parameters"]["blast_database_sequence_count"] != "2":
    raise SystemExit("BLAST database sequence count is incorrect")
if not competitive or competitive[0]["specificity_status"] != "TARGET_SPECIFIC":
    raise SystemExit("complete synthetic panel did not produce TARGET_SPECIFIC")
if evidence["analysis_outcome"] != "CANDIDATES_FOR_REVIEW" or evidence["evidence_level"] != "REVIEW" or not evidence["candidates"]:
    raise SystemExit("real BLAST candidate was lost from canonical evidence")
if "DETECTED" in json.dumps(evidence):
    raise SystemExit("uncontrolled BLAST run must not carry DETECTED")
candidate = evidence["candidates"][0]
if candidate["candidate_class"] != "LOCUS_CANDIDATE":
    raise SystemExit("real BLAST candidate has an unexpected candidate class")
# The open-analysis contract (config/evidence_profiles.json) has no
# promotion gates: candidates stay AVAILABLE with no blocking_reasons. What
# must remain explicit is that read support/coverage were not measured by
# this BLAST-only synthetic run, instead of being silently defaulted to a
# passing value.
if candidate["promotion_status"] != "AVAILABLE" or candidate["blocking_reasons"]:
    raise SystemExit("current open-analysis contract must leave candidates AVAILABLE with no blocking_reasons")
if candidate["support"]["status"] != "NOT_EVALUATED" or candidate["coverage"]["status"] != "NOT_EVALUATED":
    raise SystemExit("candidate without read remapping must explicitly report support/coverage as NOT_EVALUATED")
print("PASS: real BLAST B4 end-to-end")
PY
