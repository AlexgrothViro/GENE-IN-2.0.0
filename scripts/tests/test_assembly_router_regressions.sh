#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
TMP_DIR="$(mktemp -d /tmp/genein-router-regressions.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin"

python3 - "$TMP_DIR" <<'PY'
from pathlib import Path
import gzip
import sys

out = Path(sys.argv[1])
for mate in (1, 2):
    with gzip.open(out / f"R{mate}.fastq.gz", "wt", encoding="ascii") as handle:
        handle.write(f"@pair/{mate}\n{'A' * 150}\n+\n{'I' * 150}\n")
PY

cat >"$TMP_DIR/bin/spades.py" <<'FAKE_SPADES'
#!/usr/bin/env bash
set -euo pipefail
out=""
if [[ -n "${FAKE_SPADES_ARGS_FILE:-}" ]]; then
  printf '%s\n' "$@" > "$FAKE_SPADES_ARGS_FILE"
fi
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-o" ]]; then out="$2"; shift 2; else shift; fi
done
[[ -n "$out" ]] || exit 2
[[ "${FAKE_SPADES_RESULT:-success}" == hard ]] && exit 42
mkdir -p "$out"
if [[ "${FAKE_SPADES_RESULT:-success}" == empty ]]; then
  : > "$out/contigs.fasta"
elif [[ "${FAKE_SPADES_RESULT:-success}" == soft ]]; then
  printf '>short\n%s\n' "$(printf 'A%.0s' {1..120})" > "$out/contigs.fasta"
else
  printf '>long\n%s\n' "$(printf 'A%.0s' {1..300})" > "$out/contigs.fasta"
fi
FAKE_SPADES
cat >"$TMP_DIR/bin/velveth" <<'FAKE_VELVETH'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$1"
FAKE_VELVETH
cat >"$TMP_DIR/bin/velvetg" <<'FAKE_VELVETG'
#!/usr/bin/env bash
set -euo pipefail
out="$1"
[[ "${FAKE_VELVET_RESULT:-success}" == hard ]] && exit 43
printf '>long\n%s\n' "$(printf 'C%.0s' {1..300})" > "$out/contigs.fa"
FAKE_VELVETG
chmod +x "$TMP_DIR/bin/spades.py" "$TMP_DIR/bin/velveth" "$TMP_DIR/bin/velvetg"

run_router() {
  local assembler="$1" result="$2"
  set +e
  PATH="$TMP_DIR/bin:$PATH" PIPELINE_CONFIG_LOADED=1 SAMPLE_NAME=B3ROUTER SAMPLE_ID=B3ROUTER \
    GENEIN_WORK_ROOT="$TMP_DIR" \
    SAMPLE_R1="$TMP_DIR/R1.fastq.gz" SAMPLE_R2="$TMP_DIR/R2.fastq.gz" \
    ASSEMBLY_DIR="$TMP_DIR/$result" ASSEMBLER="$assembler" THREADS=1 \
    FAKE_SPADES_RESULT="${FAKE_SPADES_RESULT:-success}" FAKE_VELVET_RESULT="${FAKE_VELVET_RESULT:-success}" \
    ANALYSIS_PROFILE="${TEST_ANALYSIS_PROFILE:-default}" \
    bash scripts/pipeline/assembly_router.sh >/dev/null 2>&1
  local rc=$?
  set -e
  return "$rc"
}

mkdir -p "$TMP_DIR/stale/B3ROUTER_assembly"
printf '>old\n%s\n' "$(printf 'G%.0s' {1..300})" > "$TMP_DIR/stale/B3ROUTER_assembly/contigs.fa"
FAKE_SPADES_RESULT=hard FAKE_VELVET_RESULT=hard run_router spades stale || true
[[ ! -s "$TMP_DIR/stale/B3ROUTER_assembly/contigs.fa" ]]
[[ -s "$TMP_DIR/stale/B3ROUTER_assembly/contigs.previous.fa" ]]
grep -q 'ASSEMBLY_FAILURE_TYPE="HARD"' "$TMP_DIR/stale/B3ROUTER_assembly/assembly_metadata.env"

FAKE_SPADES_RESULT=soft FAKE_VELVET_RESULT=success run_router spades soft
[[ -s "$TMP_DIR/soft/B3ROUTER_assembly/contigs.fa" ]]
grep -q 'ASSEMBLY_FAILURE_TYPE="SOFT"' "$TMP_DIR/soft/B3ROUTER_assembly/assembly_metadata.env"
grep -q '^>short$' "$TMP_DIR/soft/B3ROUTER_assembly/contigs.fa"

FAKE_SPADES_RESULT=empty run_router spades empty
[[ -f "$TMP_DIR/empty/B3ROUTER_assembly/contigs.fa" && ! -s "$TMP_DIR/empty/B3ROUTER_assembly/contigs.fa" ]]
grep -q 'ASSEMBLY_FAILURE_TYPE="SOFT"' "$TMP_DIR/empty/B3ROUTER_assembly/assembly_metadata.env"

FAKE_SPADES_RESULT=empty FAKE_VELVET_RESULT=hard TEST_ANALYSIS_PROFILE=assembly-consensus run_router spades multi_empty
[[ -f "$TMP_DIR/multi_empty/B3ROUTER_assembly/contigs.fa" && ! -s "$TMP_DIR/multi_empty/B3ROUTER_assembly/contigs.fa" ]]
python3 - "$TMP_DIR/multi_empty/B3ROUTER_assembly/assembly_consensus.json" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1]))
assert manifest['sequence_count'] == 0
assert manifest['assembler_status']['spades'] == 'EMPTY'
assert not manifest['consensus_requirement_met']
PY

FAKE_SPADES_RESULT=success FAKE_VELVET_RESULT=hard run_router velvet fallback
grep -q 'ASSEMBLER_USED="spades"' "$TMP_DIR/fallback/B3ROUTER_assembly/assembly_metadata.env"
grep -q 'ASSEMBLY_FALLBACK=1' "$TMP_DIR/fallback/B3ROUTER_assembly/assembly_metadata.env"

FAKE_SPADES_ARGS_FILE="$TMP_DIR/spades-demo.args" \
  PATH="$TMP_DIR/bin:$PATH" PIPELINE_CONFIG_LOADED=1 \
  GENEIN_WORK_ROOT="$TMP_DIR" \
  R1="$TMP_DIR/R1.fastq.gz" R2="$TMP_DIR/R2.fastq.gz" \
  ASSEMBLY_DIR="$TMP_DIR/demo" \
  bash scripts/pipeline/assemblers/spades.sh DEMO 1 >/dev/null 2>&1
grep -Fxq -- '--phred-offset' "$TMP_DIR/spades-demo.args"
grep -Fxq -- '33' "$TMP_DIR/spades-demo.args"

echo "PASS router stale-output, short-contig, symmetric-fallback and SPAdes argument regressions"
