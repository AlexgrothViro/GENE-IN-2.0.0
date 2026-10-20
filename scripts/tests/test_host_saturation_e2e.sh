#!/usr/bin/env bash
# Real Bowtie2, 100%-host FASTQ input -> full scripts/pipeline/run.sh.
# Verifies the recognized host-saturation outcome end to end:
#   - the sample terminates cleanly (exit 0), without attempting assembly
#     on nonexistent FASTQs;
#   - the public receipt {sample}_execution.json carries the four
#     contracted fields: status=completed, exit_code=0,
#     technical_state=COMPLETED, scientific_call=negative_confirmed_host_saturated;
#   - no empty FASTQ was promoted into data/host_removed as valid input;
#   - the Bowtie2 log and the host_saturation.json marker are preserved.
# Also exercises the public --host-expected CLI flag end to end (true, the
# backward-compatible default), tying corrections 1 and 2 together.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

for command_name in python3 spades.py blastn blastdbcmd makeblastdb bowtie2 bowtie2-build bowtie2-inspect samtools; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "SKIP: $command_name is not installed"
    exit 77
  }
done

mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
WORK="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-host-saturation.XXXXXX")"
SAMPLE="satpath1run"

cleanup() {
  local status=$?
  if [[ "$status" -ne 0 || -n "${GENEIN_TEST_ARTIFACT_ROOT:-}" ]]; then
    echo "[ARTIFACTS] $WORK (exit=$status)" >&2
  else
    case "$WORK" in /tmp/genein-host-saturation.*) rm -rf -- "$WORK" ;; esac
  fi
}
trap cleanup EXIT

mkdir -p "$WORK/pipeline" "$WORK/blastdb" "$WORK/fastq" "$WORK/hostref"

# --- Synthetic host reference + Bowtie2 index ------------------------------
HOST_FASTA="$WORK/hostref/synthetic_host.fa"
python3 - "$HOST_FASTA" <<'PY'
import random
import sys

rng = random.Random(20260922)
seq = "".join(rng.choice("ACGT") for _ in range(600))
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(">synthetic_host\n" + seq + "\n")
PY
HOST_INDEX_PREFIX="$WORK/hostref/synthetic_host"
bowtie2-build "$HOST_FASTA" "$HOST_INDEX_PREFIX" >/dev/null

# --- Minimal target BLAST DB + manifest (required by the isolated-run gate) -
TARGET_FA="$WORK/target.fa"
printf '>target_ref\nACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT\n' > "$TARGET_FA"
BLAST_PREFIX="$WORK/blastdb/target"
makeblastdb -in "$TARGET_FA" -dbtype nucl -parse_seqids -out "$BLAST_PREFIX" >/dev/null
python3 - "$TARGET_FA" "$BLAST_PREFIX" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

reference = Path(sys.argv[1])
prefix = Path(sys.argv[2])
produced = sorted(
    path for path in prefix.parent.glob(f"{prefix.name}.*")
    if path.is_file() and not path.name.endswith(".db-manifest.json")
)

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

manifest = {
    "schema_version": "1.0",
    "logical_prefix": str(prefix),
    "generation_id": "host-saturation-e2e-20260922",
    "created_at": "2026-09-22T00:00:00+00:00",
    "source_fasta": {
        "path": str(reference), "size": reference.stat().st_size, "sha256": sha256(reference),
    },
    "produced_files": {
        path.name: {"size": path.stat().st_size, "sha256": sha256(path)} for path in produced
    },
}
Path(f"{prefix}.db-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
)
PY

# --- FASTQ input where every read pair derives from the host sequence ------
R1="$WORK/fastq/${SAMPLE}_R1.fastq.gz"
R2="$WORK/fastq/${SAMPLE}_R2.fastq.gz"
python3 - "$HOST_FASTA" "$R1" "$R2" <<'PY'
import gzip
import sys

host_path, r1_path, r2_path = sys.argv[1:4]
with open(host_path, encoding="utf-8") as handle:
    lines = handle.read().splitlines()
seq = "".join(lines[1:])
quality = "I" * 75
with gzip.open(r1_path, "wt", encoding="utf-8") as h1, gzip.open(r2_path, "wt", encoding="utf-8") as h2:
    for i in range(20):
        start = (i * 20) % (len(seq) - 75)
        h1.write(f"@hostread{i}/1\n{seq[start:start + 75]}\n+\n{quality}\n")
        h2.write(f"@hostread{i}/2\n{seq[start + 50:start + 125] if start + 125 <= len(seq) else seq[:75]}\n+\n{quality}\n")
PY

# --- Full pipeline run: 100% host saturation must short-circuit cleanly ----
set +e
env -u DB -u DB_QUERY -u REF_FASTA -u BOWTIE2_INDEX \
  GENEIN_WORK_ROOT="$WORK/pipeline" \
  BLAST_DB="$BLAST_PREFIX" \
  HOST_FILTER_ENABLED=true \
  HOST_NAME=synthetic_host \
  HOST_INDEX_PREFIX="$HOST_INDEX_PREFIX" \
  SAMPLE_R1="$R1" \
  SAMPLE_R2="$R2" \
  bash "$ROOT/scripts/pipeline/run.sh" \
    --sample "$SAMPLE" \
    --assembler spades \
    --threads 1 \
    --skip-qc \
    --host-expected true
PIPELINE_RC=$?
set -e
echo "[HOST-SATURATION-E2E] pipeline exit code: $PIPELINE_RC"
[[ "$PIPELINE_RC" -eq 0 ]] || { echo "recognized host saturation must exit 0, got $PIPELINE_RC" >&2; exit 1; }

HOST_REMOVED_DIR="$WORK/pipeline/data/host_removed"
EXECUTION_RECEIPT="$WORK/pipeline/results/reports/${SAMPLE}_execution.json"

[[ ! -f "$HOST_REMOVED_DIR/${SAMPLE}_R1.host_removed.fastq.gz" ]] || {
  echo "an empty FASTQ was promoted as valid host-removed R1 output" >&2; exit 1;
}
[[ ! -f "$HOST_REMOVED_DIR/${SAMPLE}_R2.host_removed.fastq.gz" ]] || {
  echo "an empty FASTQ was promoted as valid host-removed R2 output" >&2; exit 1;
}
[[ -s "$HOST_REMOVED_DIR/${SAMPLE}_host_filter_bowtie2.log" ]] || {
  echo "Bowtie2 log was not preserved for the recognized saturation outcome" >&2; exit 1;
}
[[ -s "$HOST_REMOVED_DIR/${SAMPLE}.host_saturation.json" ]] || {
  echo "host_saturation.json marker is missing" >&2; exit 1;
}
[[ -s "$EXECUTION_RECEIPT" ]] || {
  echo "public execution.json receipt is missing: $EXECUTION_RECEIPT" >&2; exit 1;
}
[[ ! -e "$WORK/pipeline/data/assemblies/${SAMPLE}_assembly/assembly_metadata.env" ]] || {
  echo "assembly ran after the recognized host-saturation outcome" >&2; exit 1;
}

python3 - "$EXECUTION_RECEIPT" "$HOST_REMOVED_DIR/${SAMPLE}.host_saturation.json" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
marker = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

expected = {
    "status": "completed",
    "exit_code": 0,
    "technical_state": "COMPLETED",
    "scientific_call": "negative_confirmed_host_saturated",
}
for field, value in expected.items():
    if receipt.get(field) != value:
        raise SystemExit(f"execution.json.{field} = {receipt.get(field)!r}, expected {value!r}")

if marker.get("host_saturated") is not True:
    raise SystemExit(f"host_saturation.json.host_saturated = {marker.get('host_saturated')!r}, expected True")
if marker.get("mode") != "paired":
    raise SystemExit(f"host_saturation.json.mode = {marker.get('mode')!r}, expected 'paired'")
if marker.get("host_expected") != "true":
    raise SystemExit(f"host_saturation.json.host_expected = {marker.get('host_expected')!r}, expected 'true'")

print("PASS execution.json + host_saturation.json contract fields")
PY

echo "PASS: 100% host saturation -> recognized outcome, no FASTQ promoted, execution.json contract satisfied"
