#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"
PROFILE="${REPO_ROOT}/config/experimental/direct_map_v1.json"
SAMPLE=""; RUN_ID=""; REFERENCE=""; INDEX=""; LOCI=""; R1=""; R2=""; SINGLE=""
OUT_ROOT=""; PANEL_MANIFEST=""; UMI_MODE="none"; THREADS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --sample) SAMPLE="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --reference) REFERENCE="$2"; shift 2 ;;
    --index) INDEX="$2"; shift 2 ;;
    --loci) LOCI="$2"; shift 2 ;;
    --r1) R1="$2"; shift 2 ;;
    --r2) R2="$2"; shift 2 ;;
    --single) SINGLE="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --panel-manifest) PANEL_MANIFEST="$2"; shift 2 ;;
    --umi-mode) UMI_MODE="$2"; shift 2 ;;
    --threads) THREADS="$2"; shift 2 ;;
    *) echo "[FATAL] invalid experimental direct-map option: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$SAMPLE" && -n "$RUN_ID" && -n "$REFERENCE" && -n "$INDEX" && -n "$LOCI" && -n "$OUT_ROOT" && -n "$PANEL_MANIFEST" ]] || {
  echo "[FATAL] --sample --run-id --reference --index --loci --panel-manifest --out-root are required" >&2
  exit 2
}
if [[ -n "$SINGLE" ]]; then
  [[ -z "$R1" && -z "$R2" ]] || { echo "[FATAL] use --single or --r1/--r2, not both" >&2; exit 2; }
else
  [[ -n "$R1" && -n "$R2" ]] || { echo "[FATAL] paired mode requires --r1 and --r2" >&2; exit 2; }
fi
[[ "$UMI_MODE" =~ ^(none|read_name|sam_tag)$ ]] || { echo "[FATAL] invalid --umi-mode" >&2; exit 2; }
[[ "$THREADS" =~ ^[1-9][0-9]*$ ]] || { echo "[FATAL] --threads must be a positive integer" >&2; exit 2; }
for command_name in python3 bowtie2 samtools git; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "[FATAL] missing $command_name" >&2; exit 3; }
done

python3 "${SCRIPT_DIR}/experimental_direct_map.py" validate-profile --profile "$PROFILE" >/dev/null
SAMPLE="$(python3 "${REPO_ROOT}/scripts/lib/input_validation.py" sample "$SAMPLE")"
RUN_ID="$(python3 "${REPO_ROOT}/scripts/lib/input_validation.py" run-id "$RUN_ID")"
python3 "${REPO_ROOT}/scripts/lib/input_validation.py" fasta "$REFERENCE" >/dev/null
[[ -s "$LOCI" ]] || { echo "[FATAL] loci TSV is missing or empty" >&2; exit 2; }
if [[ -n "$SINGLE" ]]; then
  python3 "${REPO_ROOT}/scripts/lib/input_validation.py" fastq "$SINGLE" >/dev/null
else
  python3 "${REPO_ROOT}/scripts/lib/input_validation.py" fastq "$R1" --mate "$R2" >/dev/null
fi
[[ -s "$PANEL_MANIFEST" ]] || { echo "[FATAL] panel manifest is missing or empty" >&2; exit 2; }
python3 "${SCRIPT_DIR}/experimental_direct_map.py" validate-panel \
  --manifest "$PANEL_MANIFEST" --reference "$REFERENCE" >/dev/null

PROFILE_VALUES="$(python3 - "$PROFILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    profile = json.load(handle)
print("\t".join((profile["aligner"]["bowtie2_version"], profile["aligner"]["samtools_version"], str(profile["aligner"]["seed"]))))
PY
)"
IFS=$'\t' read -r EXPECTED_BOWTIE2 EXPECTED_SAMTOOLS SEED <<< "$PROFILE_VALUES"
BOWTIE2_VERSION_OUTPUT="$(bowtie2 --version 2>&1)"
SAMTOOLS_VERSION_OUTPUT="$(samtools --version 2>&1)"
ACTUAL_BOWTIE2="$(printf '%s\n' "$BOWTIE2_VERSION_OUTPUT" | sed -n '/ version /{s/.* version //;p;q;}')"
ACTUAL_SAMTOOLS="$(printf '%s\n' "$SAMTOOLS_VERSION_OUTPUT" | sed -n '/^samtools /{s/^samtools //;p;q;}')"
[[ "$ACTUAL_BOWTIE2" == "$EXPECTED_BOWTIE2" ]] || {
  echo "[FATAL] Bowtie2 $EXPECTED_BOWTIE2 required by the experimental profile; found $ACTUAL_BOWTIE2" >&2
  exit 3
}
[[ "$ACTUAL_SAMTOOLS" == "$EXPECTED_SAMTOOLS" ]] || {
  echo "[FATAL] Samtools $EXPECTED_SAMTOOLS required by the experimental profile; found $ACTUAL_SAMTOOLS" >&2
  exit 3
}

INDEX_EXTENSION=""
for extension in bt2 bt2l; do
  complete=true
  for component in 1 2 3 4 rev.1 rev.2; do
    [[ -s "${INDEX}.${component}.${extension}" ]] || complete=false
  done
  if [[ "$complete" == "true" ]]; then INDEX_EXTENSION="$extension"; break; fi
done
[[ -n "$INDEX_EXTENSION" ]] || { echo "[FATAL] complete Bowtie2 index not found: $INDEX" >&2; exit 2; }

OUT_ROOT="$(python3 - "$OUT_ROOT" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve())
PY
)"
PUBLIC_EVIDENCE_ROOT="${GENEIN_PUBLIC_EVIDENCE_ROOT:-${REPO_ROOT}/results/evidence}"
PUBLIC_EVIDENCE_ROOT="$(python3 - "$PUBLIC_EVIDENCE_ROOT" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve())
PY
)"
case "$OUT_ROOT" in
  "$PUBLIC_EVIDENCE_ROOT"|"${PUBLIC_EVIDENCE_ROOT}/"*)
    echo "[FATAL] experimental output root cannot be the public Evidence V2 tree: $OUT_ROOT" >&2
    exit 2
    ;;
esac
EXPERIMENT_ROOT="${OUT_ROOT}/experimental/direct-map-v1"
STAGING_ROOT="${EXPERIMENT_ROOT}/.staging"
RUNS_ROOT="${EXPERIMENT_ROOT}/runs"
STAGING="${STAGING_ROOT}/${RUN_ID}"
FINAL="${RUNS_ROOT}/${RUN_ID}"
mkdir -p "$STAGING_ROOT" "$RUNS_ROOT"
[[ ! -e "$STAGING" && ! -e "$FINAL" ]] || {
  echo "[FATAL] run_id already has staging or final artifacts: $RUN_ID" >&2
  exit 2
}
mkdir "$STAGING"
cleanup() {
  local code=$?
  if [[ $code -ne 0 && -d "$STAGING" ]]; then
    case "$STAGING" in
      "${STAGING_ROOT}/"*) rm -rf -- "$STAGING" ;;
      *) echo "[FATAL] refusing to clean unexpected staging path: $STAGING" >&2 ;;
    esac
  fi
  exit "$code"
}
trap cleanup EXIT
cancel_run() {
  trap - INT TERM
  exit 130
}
trap cancel_run INT TERM

PRIMARY_SAM="${STAGING}/.primary.sam.tmp"
PLACEMENTS_SAM="${STAGING}/.placements.sam.tmp"
READ_ARGS=()
if [[ -n "$SINGLE" ]]; then
  READ_ARGS=(-U "$SINGLE")
else
  READ_ARGS=(-1 "$R1" -2 "$R2")
fi
PRIMARY_COMMAND=(bowtie2 --very-sensitive-local --reorder --seed "$SEED" -x "$INDEX" "${READ_ARGS[@]}" -p "$THREADS" -S "$PRIMARY_SAM")
PLACEMENTS_COMMAND=(bowtie2 --very-sensitive-local -a --reorder --seed "$SEED" -x "$INDEX" "${READ_ARGS[@]}" -p "$THREADS" -S "$PLACEMENTS_SAM")
printf -v PRIMARY_COMMAND_TEXT '%q ' "${PRIMARY_COMMAND[@]}"
printf -v PLACEMENTS_COMMAND_TEXT '%q ' "${PLACEMENTS_COMMAND[@]}"
"${PRIMARY_COMMAND[@]}" 2> "${STAGING}/bowtie2.primary.log"
"${PLACEMENTS_COMMAND[@]}" 2> "${STAGING}/bowtie2.placements.log"

build_bam() {
  local source_sam="$1" output_name="$2"
  samtools view -b -o "${STAGING}/.${output_name}.unsorted.tmp" "$source_sam"
  samtools sort -o "${STAGING}/.${output_name}.tmp" "${STAGING}/.${output_name}.unsorted.tmp"
  samtools index "${STAGING}/.${output_name}.tmp" "${STAGING}/.${output_name}.bai.tmp"
  samtools quickcheck -v "${STAGING}/.${output_name}.tmp"
  mv -f "${STAGING}/.${output_name}.tmp" "${STAGING}/${output_name}"
  mv -f "${STAGING}/.${output_name}.bai.tmp" "${STAGING}/${output_name}.bai"
  rm -f "${STAGING}/.${output_name}.unsorted.tmp"
}
build_bam "$PRIMARY_SAM" primary.bam
build_bam "$PLACEMENTS_SAM" placements.bam

SUMMARY_ARGS=(summarize --profile "$PROFILE" --sample "$SAMPLE" --run-id "$RUN_ID" \
  --reference "$REFERENCE" --index "$INDEX" --loci "$LOCI" \
  --primary-sam "$PRIMARY_SAM" --placements-sam "$PLACEMENTS_SAM" \
  --primary-bam "$STAGING/primary.bam" --placements-bam "$STAGING/placements.bam" --out-dir "$STAGING" \
  --umi-mode "$UMI_MODE" --primary-command "$PRIMARY_COMMAND_TEXT" \
  --placements-command "$PLACEMENTS_COMMAND_TEXT")
if [[ -n "$SINGLE" ]]; then
  SUMMARY_ARGS+=(--single "$SINGLE")
else
  SUMMARY_ARGS+=(--r1 "$R1" --r2 "$R2")
fi
SUMMARY_ARGS+=(--panel-manifest "$PANEL_MANIFEST")
python3 "${SCRIPT_DIR}/experimental_direct_map.py" "${SUMMARY_ARGS[@]}"
rm -f "$PRIMARY_SAM" "$PLACEMENTS_SAM"

samtools quickcheck -v "${STAGING}/primary.bam" "${STAGING}/placements.bam"
FINAL_PATH="$(python3 "${SCRIPT_DIR}/experimental_direct_map.py" finalize \
  --staging "$STAGING" --final "$FINAL" --run-id "$RUN_ID")"
trap - EXIT INT TERM
echo "[OK] EXPERIMENTAL direct-map run: $FINAL_PATH"
echo "[RUN_ID] $RUN_ID"
