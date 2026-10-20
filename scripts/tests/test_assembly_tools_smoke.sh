#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
TMP_DIR="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-assembly-smoke.XXXXXX")"
if [[ "${KEEP_SMOKE_ARTIFACTS:-0}" == "1" || -n "${GENEIN_TEST_ARTIFACT_ROOT:-}" ]]; then
  trap 'echo "SMOKE_TMP=$TMP_DIR" >&2' EXIT
else
  cleanup() {
    local cleanup_status=$?
    if [[ $cleanup_status -ne 0 ]]; then
      echo "SMOKE_TMP=$TMP_DIR (exit=$cleanup_status)" >&2
    else
      rm -rf -- "$TMP_DIR"
    fi
  }
  trap cleanup EXIT
fi

python3 - "$TMP_DIR" <<'PY'
from pathlib import Path
import gzip
import random
import sys

out = Path(sys.argv[1])
rng = random.Random(7)
genome = "".join(rng.choice("ACGT") for _ in range(5000))
complement = str.maketrans("ACGT", "TGCA")

def revcomp(sequence: str) -> str:
    return sequence.translate(complement)[::-1]

with gzip.open(out / "R1.fastq.gz", "wt", encoding="ascii") as r1, gzip.open(out / "R2.fastq.gz", "wt", encoding="ascii") as r2:
    for index in range(1200):
        start = (index * 37) % 4700
        left = genome[start:start + 150]
        right = revcomp(genome[start:start + 150])
        r1.write(f"@read{index}/1\n{left}\n+\n{'I' * 150}\n")
        r2.write(f"@read{index}/2\n{right}\n+\n{'I' * 150}\n")
PY

run_and_check() {
  local assembler="$1" output="$2" fasta="$3"
  mkdir -p "$output"
  if [[ "$assembler" == "velvet" ]]; then
    PIPELINE_CONFIG_LOADED=1 R1="$TMP_DIR/R1.fastq.gz" R2="$TMP_DIR/R2.fastq.gz" \
      ASSEMBLY_DIR="$output" THREADS=2 \
      timeout 180 bash "scripts/pipeline/assemblers/${assembler}.sh" B3SYNTH 31 >"$TMP_DIR/${assembler}.log" 2>&1
  else
    PIPELINE_CONFIG_LOADED=1 SPADES_PARAMS="-m 4 --phred-offset 33" R1="$TMP_DIR/R1.fastq.gz" R2="$TMP_DIR/R2.fastq.gz" \
      ASSEMBLY_DIR="$output" THREADS=2 \
      timeout 180 bash "scripts/pipeline/assemblers/${assembler}.sh" B3SYNTH 2 "-m 4 --phred-offset 33" >"$TMP_DIR/${assembler}.log" 2>&1
  fi
  [[ -s "$fasta" ]] || { echo "missing contigs for $assembler" >&2; cat "$TMP_DIR/${assembler}.log" >&2; return 1; }
  python3 scripts/lib/input_validation.py fasta "$fasta" >/dev/null
  echo "PASS $assembler $(grep -c '^>' "$fasta") contigs"
}

run_and_check velvet "$TMP_DIR/velvet" "$TMP_DIR/velvet/B3SYNTH_velvet_k31/contigs.fa"
run_and_check spades "$TMP_DIR/spades" "$TMP_DIR/spades/B3SYNTH_spades/contigs.fasta"
run_and_check metaspades "$TMP_DIR/metaspades" "$TMP_DIR/metaspades/B3SYNTH_metaspades/contigs.fasta"
