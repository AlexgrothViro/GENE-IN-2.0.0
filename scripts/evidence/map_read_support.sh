#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SAMPLE=""; INDEX=""; REFERENCE=""; R1=""; R2=""; OUTDIR=""; LOCI=""
LIBRARY_MODE="unknown"; UMI_MODE="none"; UMI_SEED=1; MIN_MAPQ=10; MIN_BASEQ=20; WINDOW_BP=100; THREADS=4
RUN_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample) SAMPLE="$2"; shift 2 ;;
    --index) INDEX="$2"; shift 2 ;;
    --reference) REFERENCE="$2"; shift 2 ;;
    --r1) R1="$2"; shift 2 ;;
    --r2) R2="$2"; shift 2 ;;
    --out-dir) OUTDIR="$2"; shift 2 ;;
    --loci) LOCI="$2"; shift 2 ;;
    --library-mode) LIBRARY_MODE="$2"; shift 2 ;;
    --umi-mode) UMI_MODE="$2"; shift 2 ;;
    --umi-seed) UMI_SEED="$2"; shift 2 ;;
    --minimum-mapq) MIN_MAPQ="$2"; shift 2 ;;
    --minimum-base-quality) MIN_BASEQ="$2"; shift 2 ;;
    --window-bp) WINDOW_BP="$2"; shift 2 ;;
    --threads) THREADS="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    *) echo "[FATAL] invalid map_read_support option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$SAMPLE" && -n "$INDEX" && -n "$REFERENCE" && -n "$R1" && -n "$R2" && -n "$OUTDIR" ]] || {
  echo "[FATAL] --sample --index --reference --r1 --r2 --out-dir are required" >&2; exit 2;
}
[[ -n "$RUN_ID" ]] || { echo "[FATAL] --run-id is required for template lineage" >&2; exit 2; }
for cmd in bowtie2 bowtie2-inspect samtools python3; do command -v "$cmd" >/dev/null 2>&1 || { echo "[FATAL] missing $cmd" >&2; exit 3; }; done
mkdir -p "$OUTDIR"
TMPDIR_RUN="$(mktemp -d "${OUTDIR}/.mapping.XXXXXX")"
trap 'rm -rf "$TMPDIR_RUN"' EXIT

write_header_only_lineage() {
  python3 "$SCRIPT_DIR/build_template_lineage.py" \
    --header-only --out "$OUTDIR/template_lineage.tsv" \
    --run-id "$RUN_ID" --sample "$SAMPLE" --library-mode "$LIBRARY_MODE" --umi-mode "$UMI_MODE" \
    2>/dev/null || true
  if [[ ! -s "$OUTDIR/template_lineage.tsv" ]]; then
    printf 'lineage_record_id\tlineage_id\tsample_id\treference_id\tlocus_id\torientation\tquery_ids\tsource_template_digests\tfinal_umi\tumi_group_method\tlibrary_mode\tumi_mode\ttemplate_count\tread_count\tmapped_bases\tproper_pair_templates\tdiscordant_templates\teligible\trejection_reason\trule_id\n' \
      > "$OUTDIR/template_lineage.tsv"
  fi
}


REFERENCE_CHECK_ARGS=(--index "$INDEX" --reference "$REFERENCE" --out "$OUTDIR/mapping_reference_check.json")
[[ -z "$LOCI" ]] || REFERENCE_CHECK_ARGS+=(--loci "$LOCI")
python3 "$SCRIPT_DIR/validate_mapping_reference.py" "${REFERENCE_CHECK_ARGS[@]}"
bowtie2 --very-sensitive-local -x "$INDEX" -1 "$R1" -2 "$R2" -p "$THREADS" -S "$TMPDIR_RUN/raw.sam" 2> "$OUTDIR/bowtie2.log"
samtools view -b -F 2304 -q "$MIN_MAPQ" "$TMPDIR_RUN/raw.sam" | samtools sort -n -o "$TMPDIR_RUN/name.bam"
samtools fixmate -m "$TMPDIR_RUN/name.bam" "$TMPDIR_RUN/fixmate.bam"
samtools sort -o "$TMPDIR_RUN/coordinate.bam" "$TMPDIR_RUN/fixmate.bam"
samtools index "$TMPDIR_RUN/coordinate.bam"

LINEAGE_SAM="$TMPDIR_RUN/lineage.sam"

if [[ "$UMI_MODE" == "none" ]]; then
  # Sem UMI não há identidade molecular para remoção segura. A deduplicação fica
  # desativada por padrão em todas as bibliotecas e seu uso futuro exigirá análise
  # de sensibilidade explicitamente versionada.
  cp -f "$TMPDIR_RUN/coordinate.bam" "$TMPDIR_RUN/deduplicated.bam"
  samtools view -h "$TMPDIR_RUN/coordinate.bam" > "$LINEAGE_SAM"
else
  if ! command -v umi_tools >/dev/null 2>&1; then
    echo "[FATAL] umi_tools is required when umi_mode=$UMI_MODE" >&2
    exit 3
  fi
  UMI_ARGS=(
    --method=directional
    --edit-distance-threshold=1
    --random-seed "$UMI_SEED"
    --paired
  )
  if [[ "$UMI_MODE" == "read_name" ]]; then
    UMI_ARGS+=(--extract-umi-method=read_id)
  else
    UMI_ARGS+=(--extract-umi-method=tag --umi-tag=RX)
  fi
  # Group annotates UG/BX for template_lineage; dedup still feeds read_support summary.
  umi_tools group "${UMI_ARGS[@]}" --output-bam \
    --stdin "$TMPDIR_RUN/coordinate.bam" --stdout "$TMPDIR_RUN/grouped.bam"
  umi_tools dedup "${UMI_ARGS[@]}" \
    --stdin "$TMPDIR_RUN/coordinate.bam" --stdout "$TMPDIR_RUN/deduplicated.bam"
  samtools view -h "$TMPDIR_RUN/grouped.bam" > "$LINEAGE_SAM"
fi

samtools index "$TMPDIR_RUN/deduplicated.bam"
samtools quickcheck -v "$TMPDIR_RUN/deduplicated.bam"
samtools view -h "$TMPDIR_RUN/deduplicated.bam" > "$TMPDIR_RUN/deduplicated.sam"
LOCI_ARGS=()
[[ -n "$LOCI" ]] && LOCI_ARGS=(--loci "$LOCI")
python3 "$SCRIPT_DIR/summarize_read_support.py" --sam "$TMPDIR_RUN/deduplicated.sam" --sample "$SAMPLE" \
  --library-mode "$LIBRARY_MODE" --umi-mode "$UMI_MODE" --minimum-mapq "$MIN_MAPQ" \
  "${LOCI_ARGS[@]}" --out "$OUTDIR/read_support.tsv"
samtools depth -aa -q "$MIN_BASEQ" -Q "$MIN_MAPQ" "$TMPDIR_RUN/deduplicated.bam" > "$TMPDIR_RUN/depth.tsv"
python3 "$SCRIPT_DIR/summarize_coverage.py" --depth "$TMPDIR_RUN/depth.tsv" --reference-fasta "$REFERENCE" \
  "${LOCI_ARGS[@]}" --window-bp "$WINDOW_BP" --minimum-mapq "$MIN_MAPQ" \
  --minimum-base-quality "$MIN_BASEQ" --out "$OUTDIR/coverage.tsv"

LINEAGE_ARGS=(
  --sam "$LINEAGE_SAM"
  --loci "$LOCI"
  --out "$OUTDIR/template_lineage.tsv"
  --run-id "$RUN_ID"
  --sample "$SAMPLE"
  --library-mode "$LIBRARY_MODE"
  --umi-mode "$UMI_MODE"
)
if [[ -z "$LOCI" || ! -s "$LOCI" ]]; then
  write_header_only_lineage
else
  python3 "$SCRIPT_DIR/build_template_lineage.py" "${LINEAGE_ARGS[@]}"
fi

cp -f "$TMPDIR_RUN/deduplicated.bam" "$OUTDIR/read_support.bam.tmp"
cp -f "$TMPDIR_RUN/deduplicated.bam.bai" "$OUTDIR/read_support.bam.bai.tmp"
mv -f "$OUTDIR/read_support.bam.tmp" "$OUTDIR/read_support.bam"
mv -f "$OUTDIR/read_support.bam.bai.tmp" "$OUTDIR/read_support.bam.bai"
