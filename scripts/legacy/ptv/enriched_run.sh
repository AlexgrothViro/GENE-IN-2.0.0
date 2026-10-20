#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

CONFIG_FILE="${REPO_ROOT}/config/picornavirus.env"
LEGACY_CONFIG="${REPO_ROOT}/config.env"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
elif [[ -f "${LEGACY_CONFIG}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${LEGACY_CONFIG}"
fi

source "${SCRIPTS_ROOT}/lib/common.sh"
SAMPLE_IN="${1:?SAMPLE obrigatório}"
KMER="${2:?KMER obrigatório}"

RAW_DIR="$(resolve_path "${RAW_DIR:-data/raw}")"
ASSEMBLY_DIR="$(resolve_path "${ASSEMBLY_DIR:-data/assemblies}")"
PTV_ENRICHED_DIR="$(resolve_path "${PTV_ENRICHED_DIR:-data/ptv_enriched}")"
RESULTS_DIR="$(resolve_path "${RESULTS_DIR:-results}")"
BOWTIE2_INDEX="$(resolve_path "${BOWTIE2_INDEX:-bowtie2/${DB:-ptv}}")"
BLAST_DB_PATH="$(resolve_path "${BLAST_DB:-blastdb/${DB:-ptv}}")"

# aceita SAMPLE=XXXX_PTV ou SAMPLE=XXXX
if [[ "$SAMPLE_IN" == *_PTV ]]; then
  BASE="${SAMPLE_IN%_PTV}"
  PTV_SAMPLE="$SAMPLE_IN"
else
  BASE="$SAMPLE_IN"
  PTV_SAMPLE="${SAMPLE_IN}_PTV"
fi

RAW1="${RAW_DIR}/${BASE}_R1.fastq.gz"
RAW2="${RAW_DIR}/${BASE}_R2.fastq.gz"

mkdir -p "$RAW_DIR" "$PTV_ENRICHED_DIR" "$RESULTS_DIR/qc" "$RESULTS_DIR/phylogeny"

check_file "$RAW1"
check_file "$RAW2"

# 1) Bowtie2 enrichment
PREFIX="${PTV_ENRICHED_DIR}/${BASE}_ptv.fastq.gz"
ENR1="${PTV_ENRICHED_DIR}/${BASE}_ptv.fastq.1.gz"
ENR2="${PTV_ENRICHED_DIR}/${BASE}_ptv.fastq.2.gz"
LOG="${RESULTS_DIR}/qc/${BASE}_ptv_map.log"

rm -f "$ENR1" "$ENR2" "$LOG" 2>/dev/null || true

log_info "Bowtie2 enrich (index=$BOWTIE2_INDEX) ..."
bowtie2 -x "$BOWTIE2_INDEX" \
  -1 "$RAW1" -2 "$RAW2" \
  --very-sensitive-local \
  --al-conc-gz "$PREFIX" \
  -S /dev/null 2> "$LOG"

# 2) Symlinks para o padrão do pipeline (RAW_DIR/<SAMPLE>_R1.fastq.gz)
ln -sf "${ENR1}" "${RAW_DIR}/${PTV_SAMPLE}_R1.fastq.gz"
ln -sf "${ENR2}" "${RAW_DIR}/${PTV_SAMPLE}_R2.fastq.gz"

# 3) Velvet
log_info "Velvet (sample=$PTV_SAMPLE k=$KMER) ..."
"${SCRIPTS_ROOT}/pipeline/assemblers/velvet.sh" "$PTV_SAMPLE" "$KMER"

# 4) BLAST (por kmer)
log_info "BLAST (sample=$PTV_SAMPLE k=$KMER db=$BLAST_DB_PATH) ..."
BLAST_DB="$BLAST_DB_PATH" "${SCRIPT_DIR}/blast.sh" "$PTV_SAMPLE" "$KMER"

# 5) Extract hits
log_info "Extract hits ..."
(
  cd "$REPO_ROOT"
  python3 "${SCRIPTS_ROOT}/pipeline/extract_hits.py" --sample "$PTV_SAMPLE" --kmer "$KMER"
)

OUT="${RESULTS_DIR}/phylogeny/${PTV_SAMPLE}_k${KMER}"

# 6) MAFFT (refs + addfragments)
command -v mafft >/dev/null || log_error "mafft não instalado: sudo apt-get install -y mafft"

log_info "MAFFT refs ..."
mafft --auto "$OUT/refs.fa" > "$OUT/refs.aln.fa"

log_info "MAFFT addfragments ..."
mafft --addfragments "$OUT/hits.fa" --keeplength "$OUT/refs.aln.fa" > "$OUT/ptv_fragments.aln.fa"

# 7) Report (curto e objetivo)
REPORT="$OUT/report.txt"
{
  echo "sample_base=$BASE"
  echo "sample_ptv=$PTV_SAMPLE"
  echo "kmer=$KMER"
  echo "bowtie2_index=$BOWTIE2_INDEX"
  echo "blast_db=$BLAST_DB_PATH"
echo

  echo "== Bowtie2 (últimas 12 linhas do log) =="
  tail -n 12 "$LOG" || true
echo

  echo "== Enriched pairs =="
  for f in "$ENR1" "$ENR2"; do
    printf "%s\t" "$f"
    zcat "$f" | awk 'END{print NR/4" reads"}'
  done
echo

  echo "== Assembly contigs (contigs.fa) =="
  CONTIGS="${ASSEMBLY_DIR}/${PTV_SAMPLE}_velvet_k${KMER}/contigs.fa"
  awk 'BEGIN{n=0}
    /^>/ {if(n>0){c++; sum+=n; if(n>max)max=n; if(n>=200)c200++; if(n>=500)c500++; n=0; next} next}
    {n+=length($0)}
    END{if(n>0){c++; sum+=n; if(n>max)max=n; if(n>=200)c200++; if(n>=500)c500++}
    printf("contigs=%d\ttotal_bp=%d\tmax=%d\t>=200=%d\t>=500=%d\n", c,sum,max,c200+0,c500+0)}' "$CONTIGS"
echo

echo "== hits.fa lengths =="
    lens_tmp="$(mktemp)"
    awk 'BEGIN{RS=">";FS="\n"} NR>1 {seq=""; for(i=2;i<=NF;i++) seq=seq $i; print length(seq)}' "$OUT/hits.fa" | sort -n > "$lens_tmp"

    ct=$(awk 'END{print NR+0}' "$lens_tmp")
    if [ "$ct" -eq 0 ]; then
      echo "seqs=0"
    else
      min=$(head -n1 "$lens_tmp")
      max=$(tail -n1 "$lens_tmp")
      p50_line=$(( (ct-1)*50/100 + 1 ))
      p90_line=$(( (ct-1)*90/100 + 1 ))
      p50=$(awk -v n="$p50_line" 'NR==n{print; exit}' "$lens_tmp")
      p90=$(awk -v n="$p90_line" 'NR==n{print; exit}' "$lens_tmp")
      read mean ge50 ge80 ge120 ge200 <<<"$(awk '{sum+=$1; if($1>=50)ge50++; if($1>=80)ge80++; if($1>=120)ge120++; if($1>=200)ge200++}
        END{printf "%.2f %d %d %d %d", (NR?sum/NR:0), ge50+0, ge80+0, ge120+0, ge200+0}' "$lens_tmp")"
      echo "seqs=$ct min=$min p50=$p50 p90=$p90 max=$max mean=$mean | >=50=$ge50 >=80=$ge80 >=120=$ge120 >=200=$ge200"
    fi
    rm -f "$lens_tmp"
echo

echo

# ---- optional: stop after alignment (no postprocess / no tree) ----
if [ "${STOP_AFTER_ALIGN:-0}" -eq 1 ]; then
  log_info "STOP_AFTER_ALIGN=1: parando após MAFFT (sem postprocess/árvore)."
  # Evita confusão com outputs antigos de árvore/cobertura no mesmo OUTDIR
  mkdir -p "$OUT/_old_tree"
  for f in "$OUT"/ptv_fasttree*.nwk "$OUT"/tree_input*.aln.fa "$OUT"/coverage_*.tsv; do
    [ -e "$f" ] && mv -f "$f" "$OUT/_old_tree/"
  done
  echo "Report: $REPORT"
  exit 0
fi
python3 "${SCRIPT_DIR}/postprocess.py" --outdir "$OUT" --max-frags 200 --min-frag-acgt 80 --prefix tree_input
echo
  echo "Arquivos extra (cobertura/árvore):"
  echo "  $OUT/coverage_by_ref.tsv"
  echo "  $OUT/coverage_intervals_by_ref.tsv"
  echo "  $OUT/tree_input.aln.fa"

echo "OK: alinhamentos gerados:"
  echo "  $OUT/refs.aln.fa"
  echo "  $OUT/ptv_fragments.aln.fa"
} > "$REPORT"

# ---- FastTree (árvore) ----
# - remove ref curta PX101488.1
# - normaliza ambiguidades (qualquer coisa fora de ACGTNacgtn- vira N)
if command -v fasttree >/dev/null 2>&1; then
  TREE_IN="$OUT/tree_input.aln.fa"
  TREE_IN_NOPX="$OUT/tree_input.noPX.clean.aln.fa"
  TREE_NWK="$OUT/ptv_fasttree.nwk"

  awk 'BEGIN{RS=">"; ORS=""}
       NR>1{
         n=split($0,a,"\n");
         hdr=a[1]; sub(/ .*/,"",hdr);
         if(hdr=="PX101488.1") next;
         seq="";
         for(i=2;i<=n;i++) seq=seq a[i];
         gsub(/[^ACGTNacgtn-]/,"N",seq);
         print ">"hdr"\n"seq"\n";
       }' "$TREE_IN" > "$TREE_IN_NOPX"

  fasttree -nt -gtr "$TREE_IN_NOPX" > "$TREE_NWK"
  echo "tree_input_clean=$TREE_IN_NOPX" >> "$REPORT"
  echo "tree_nwk=$TREE_NWK" >> "$REPORT"
else
  echo "FastTree não encontrado. Instale com: sudo apt install fasttree" >> "$REPORT"
fi


log_info "OK: pipeline PTV-enriched concluído."
echo "Report: $REPORT"
tail -n 80 "$REPORT"
