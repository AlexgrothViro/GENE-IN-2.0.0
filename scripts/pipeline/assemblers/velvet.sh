#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

usage() {
  cat <<'USAGE' >&2
Uso:
  bash scripts/pipeline/assemblers/velvet.sh SAMPLE [KMER]

Regras:
- SAMPLE passado por argumento SEMPRE vence.
- Procura reads em: data/host_removed -> data/cleaned -> data/raw
USAGE
}

SAMPLE_NAME="${1:-}"
SAMPLE_NAME="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE_NAME")"
KMER="${2:-${VELVET_K:-31}}"
THREADS="${THREADS:-4}"
MIN_CONTIG_LEN="${MIN_CONTIG_LEN:-20}"
VELVET_EXTRA_OPTS="${3:-}"
read -r -a VELVET_EXTRA_ARGS <<< "$VELVET_EXTRA_OPTS"

[[ -z "$SAMPLE_NAME" ]] && usage && exit 1

pick_reads_paired() {
  local s="$1"
  for d in "data/host_removed" "data/cleaned" "data/raw"; do
    local r1="${REPO_ROOT}/${d}/${s}_R1.fastq.gz"
    local r2="${REPO_ROOT}/${d}/${s}_R2.fastq.gz"
    if [[ -s "$r1" && -s "$r2" ]]; then
      echo "$r1|$r2|$d"
      return 0
    fi
  done
  return 1
}

pick_reads_single() {
  local s="$1"
  for d in "data/host_removed" "data/cleaned" "data/raw"; do
    local se="${REPO_ROOT}/${d}/${s}.fastq.gz"
    if [[ -s "$se" ]]; then
      echo "$se|$d"
      return 0
    fi
  done
  return 1
}

SINGLE_INPUT="${SAMPLE_SINGLE:-}"
R1_INPUT="${R1:-}"
R2_INPUT="${R2:-}"

if [[ -n "$SINGLE_INPUT" && ( -n "$R1_INPUT" || -n "$R2_INPUT" ) ]]; then
  echo "[ERRO] Use entrada single-end ou paired-end, nunca ambas." >&2
  exit 2
fi
if [[ -n "$SINGLE_INPUT" ]]; then
  SINGLE_PATH="$SINGLE_INPUT"
  [[ "$SINGLE_PATH" = /* ]] || SINGLE_PATH="${REPO_ROOT}/${SINGLE_PATH}"
  [[ -s "$SINGLE_PATH" ]] || { echo "[ERRO] SAMPLE_SINGLE não encontrado: $SINGLE_PATH" >&2; exit 1; }
  MODE="single"
elif [[ -n "$R1_INPUT" && -n "$R2_INPUT" ]]; then
  R1="$R1_INPUT"; R2="$R2_INPUT"
  [[ "$R1" = /* ]] || R1="${REPO_ROOT}/${R1}"
  [[ "$R2" = /* ]] || R2="${REPO_ROOT}/${R2}"
  [[ -s "$R1" && -s "$R2" ]] || { echo "[ERRO] R1/R2 informados não encontrados." >&2; exit 1; }
  MODE="paired"
elif picked="$(pick_reads_paired "$SAMPLE_NAME")"; then
  R1="${picked%%|*}"; rest="${picked#*|}"
  R2="${rest%%|*}"; SRC_DIR="${rest#*|}"
  MODE="paired"
elif picked_single="$(pick_reads_single "$SAMPLE_NAME")"; then
  SINGLE_PATH="${picked_single%%|*}"; SRC_DIR="${picked_single#*|}"
  MODE="single"
else
  echo "[ERRO] FASTQs não encontrados para SAMPLE='$SAMPLE_NAME'." >&2
  echo "       Procurei em: data/host_removed, data/cleaned, data/raw" >&2
  echo "[DICA] Amostras em data/raw:" >&2
  find "${REPO_ROOT}/data/raw" -maxdepth 1 -type f -name '*_R1.fastq.gz' -printf '%f\n' 2>/dev/null | sed -E 's/_R1\.fastq\.gz$//' | sort -u | sed 's/^/  - /' >&2 || true
  exit 1
fi

ASSEMBLY_DIR="${ASSEMBLY_DIR:-${REPO_ROOT}/data/assemblies}"
if [[ "$ASSEMBLY_DIR" != /* ]]; then ASSEMBLY_DIR="${REPO_ROOT}/${ASSEMBLY_DIR}"; fi
mkdir -p "$ASSEMBLY_DIR"
OUTDIR="${ASSEMBLY_DIR}/${SAMPLE_NAME}_velvet_k${KMER}"
ATTEMPT_DIR="$(mktemp -d "${ASSEMBLY_DIR}/.${SAMPLE_NAME}_velvet_k${KMER}.XXXXXX")"
trap 'rm -rf "$ATTEMPT_DIR"' EXIT

if ! [[ "$KMER" =~ ^[0-9]+$ ]] || (( KMER < 15 || KMER > 127 || KMER % 2 == 0 )); then
  echo "[ERRO] KMER deve ser impar e estar entre 15 e 127: $KMER" >&2
  exit 2
fi
if ! [[ "$THREADS" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ERRO] THREADS deve ser um inteiro positivo: $THREADS" >&2
  exit 2
fi
if [[ "$MODE" == "single" ]]; then
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$SINGLE_PATH" >/dev/null || exit 2
else
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$R1" --mate "$R2" >/dev/null || exit 2
fi

echo "[INFO] Velvet: SAMPLE=$SAMPLE_NAME KMER=$KMER"
echo "[INFO] Reads: ${SRC_DIR:-custom}"
echo "[INFO] Out: $OUTDIR"

if [[ "$MODE" == "single" ]]; then
  echo "[INFO] Modo single-end: $SINGLE_PATH"
  if [[ "$SINGLE_PATH" == *.gz ]]; then READ_FORMAT="-fastq.gz"; else READ_FORMAT="-fastq"; fi
  velveth "$ATTEMPT_DIR" "$KMER" -short "$READ_FORMAT" "$SINGLE_PATH"
else
  if [[ "$R1" == *.gz && "$R2" == *.gz ]]; then
    READ_FORMAT="-fastq.gz"
  elif [[ "$R1" != *.gz && "$R2" != *.gz ]]; then
    READ_FORMAT="-fastq"
  else
    echo "[ERRO] R1 e R2 devem ter o mesmo formato de compressao." >&2
    exit 2
  fi
  velveth "$ATTEMPT_DIR" "$KMER" -shortPaired "$READ_FORMAT" -separate "$R1" "$R2"
fi
READ_TRKG="${READ_TRKG:-yes}"

if velvetg "$ATTEMPT_DIR" -exp_cov auto -cov_cutoff auto -read_trkg "$READ_TRKG" -min_contig_lgth "$MIN_CONTIG_LEN" "${VELVET_EXTRA_ARGS[@]}"; then
  :
else
  exit_code=$?
  if [[ $exit_code -eq 139 ]]; then
    echo "[ERRO] Velvet falhou com segmentation fault (exit code 139)." >&2
    echo "       Causas prováveis:" >&2
    echo "       - Limitação estrutural ou bug do Velvet para esse dataset específico." >&2
    echo "       - Lentidão extrema ou erros ao rodar dentro do diretório do Windows (/mnt/c) via WSL." >&2
    echo "       - Falta de memória RAM para a quantidade de reads." >&2
    echo "       - Incompatibilidade com os parâmetros de montagem ou tamanho de k-mer." >&2
    echo "" >&2
    echo "[DICA] Recomendamos trocar o montador:" >&2
    echo "       make pipeline SAMPLE=$SAMPLE_NAME ASSEMBLER=spades" >&2
    echo "       make pipeline SAMPLE=$SAMPLE_NAME ASSEMBLER=metaspades" >&2
  else
    echo "[ERRO] velvetg falhou com exit code $exit_code." >&2
  fi
  exit $exit_code
fi
# velvetg already returned 0 here. A contigs.fa that EXISTS and is EMPTY (e.g.
# "EMPTY GRAPH") is a completed attempt with zero contigs: publish it empty so
# assembly_router.sh records SOFT. Missing or invalid output stays fatal.
if [[ -f "$ATTEMPT_DIR/contigs.fa" && ! -s "$ATTEMPT_DIR/contigs.fa" ]]; then
  echo "[AVISO] Velvet concluiu sem contigs (contigs.fa presente e vazio); publicando FASTA vazio." >&2
else
  [[ -s "$ATTEMPT_DIR/contigs.fa" ]] || { echo "[ERRO] Velvet nao gerou contigs.fa na tentativa atual" >&2; exit 1; }
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$ATTEMPT_DIR/contigs.fa" >/dev/null || {
    echo "[ERRO] Velvet gerou FASTA invalido" >&2
    exit 1
  }
fi
mkdir -p "$OUTDIR"
CONTIGS_TMP="$(mktemp "${OUTDIR}/.contigs.fa.XXXXXX")"
cp -f "$ATTEMPT_DIR/contigs.fa" "$CONTIGS_TMP"
mv -f "$CONTIGS_TMP" "$OUTDIR/contigs.fa"
echo "[OK] Contigs: $OUTDIR/contigs.fa"
