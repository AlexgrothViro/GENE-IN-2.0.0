#!/usr/bin/env bash
# Adaptador opcional do pacote genein-builder. Nao entra no caminho padrao.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

usage() {
  cat <<'USAGE' >&2
Uso:
  bash scripts/pipeline/assemblers/builder.sh SAMPLE [THREADS]

Le os mesmos FASTQs pos-QC que o roteador ja selecionou (R1/R2 ou SAMPLE_SINGLE).
Sem esses caminhos, procura em data/host_removed, data/cleaned e data/raw.
BUILDER_MOTOR escolhe o motor do Builder 0.4.0: v1 (padrao) ou megahit.
THREADS e o argumento do roteador Gene-In; vai como -t so com o megahit.
O Builder nao tem --single. Entrada simples segue como --r1, sem --r2.
O pacote genein-builder e opcional. Se estiver ausente, o script encerra com
erro explicito e nao escolhe outro montador.
USAGE
}

SAMPLE_NAME="${1:-}"
SAMPLE_NAME="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE_NAME")"
THREADS="${2:-${THREADS:-4}}"
if ! [[ "$THREADS" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ERRO] THREADS deve ser um inteiro positivo: $THREADS" >&2
  exit 2
fi
BUILDER_MOTOR="${BUILDER_MOTOR:-v1}"
case "$BUILDER_MOTOR" in
  v1) MOTOR_ARGS=(--motor v1) ;;
  megahit) MOTOR_ARGS=(--motor megahit --threads "$THREADS") ;;
  *)
    echo "[ERRO] BUILDER_MOTOR deve ser v1 ou megahit: $BUILDER_MOTOR" >&2
    exit 2
    ;;
esac

pick_reads_paired() {
  local sample="$1"
  local directory
  for directory in "data/host_removed" "data/cleaned" "data/raw"; do
    local read1="${REPO_ROOT}/${directory}/${sample}_R1.fastq.gz"
    local read2="${REPO_ROOT}/${directory}/${sample}_R2.fastq.gz"
    if [[ -s "$read1" && -s "$read2" ]]; then
      printf '%s|%s\n' "$read1" "$read2"
      return 0
    fi
  done
  return 1
}

pick_reads_single() {
  local sample="$1"
  local directory
  for directory in "data/host_removed" "data/cleaned" "data/raw"; do
    local single="${REPO_ROOT}/${directory}/${sample}.fastq.gz"
    if [[ -s "$single" ]]; then
      printf '%s\n' "$single"
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

MODE="paired"
if [[ -n "$SINGLE_INPUT" ]]; then
  SINGLE_PATH="$SINGLE_INPUT"
  [[ "$SINGLE_PATH" = /* ]] || SINGLE_PATH="${REPO_ROOT}/${SINGLE_PATH}"
  MODE="single"
elif [[ -n "$R1_INPUT" || -n "$R2_INPUT" ]]; then
  [[ -n "$R1_INPUT" && -n "$R2_INPUT" ]] || {
    echo "[ERRO] R1 e R2 devem ser informados juntos." >&2
    exit 2
  }
  R1="$R1_INPUT"
  R2="$R2_INPUT"
  [[ "$R1" = /* ]] || R1="${REPO_ROOT}/${R1}"
  [[ "$R2" = /* ]] || R2="${REPO_ROOT}/${R2}"
elif picked="$(pick_reads_paired "$SAMPLE_NAME")"; then
  R1="${picked%%|*}"
  R2="${picked#*|}"
elif picked_single="$(pick_reads_single "$SAMPLE_NAME")"; then
  SINGLE_PATH="$picked_single"
  MODE="single"
else
  echo "[ERRO] FASTQs nao encontrados para SAMPLE='$SAMPLE_NAME'." >&2
  echo "       Procurei em: data/host_removed, data/cleaned, data/raw" >&2
  exit 1
fi

if [[ "$MODE" == "single" ]]; then
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$SINGLE_PATH" >/dev/null
else
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$R1" --mate "$R2" >/dev/null
fi

ASSEMBLY_DIR="${ASSEMBLY_DIR:-${REPO_ROOT}/data/assemblies}"
if [[ "$ASSEMBLY_DIR" != /* ]]; then
  ASSEMBLY_DIR="${REPO_ROOT}/${ASSEMBLY_DIR}"
fi
OUTDIR="${ASSEMBLY_DIR}/${SAMPLE_NAME}_builder"
mkdir -p "$OUTDIR"

if [[ "$BUILDER_MOTOR" == "megahit" ]]; then
  echo "[INFO] Builder: SAMPLE=$SAMPLE_NAME motor=megahit (-t $THREADS)"
else
  echo "[INFO] Builder: SAMPLE=$SAMPLE_NAME motor=v1 (threads do Gene-In=$THREADS; nao repassado)"
fi
if [[ "$MODE" == "single" ]]; then
  echo "[INFO] Reads single-end: $SINGLE_PATH"
  python3 "${SCRIPT_DIR}/builder_adapter.py" run \
    --sample "$SAMPLE_NAME" \
    --r1 "$SINGLE_PATH" \
    --outdir "$OUTDIR" \
    "${MOTOR_ARGS[@]}"
else
  echo "[INFO] Reads paired-end: $R1 / $R2"
  python3 "${SCRIPT_DIR}/builder_adapter.py" run \
    --sample "$SAMPLE_NAME" \
    --r1 "$R1" \
    --r2 "$R2" \
    --outdir "$OUTDIR" \
    "${MOTOR_ARGS[@]}"
fi
