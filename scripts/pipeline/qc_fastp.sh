#!/usr/bin/env bash
# =============================================================================
# qc_fastp.sh — Controle de qualidade com fastp
# =============================================================================
# Objetivo: Trimagem de adaptadores, filtragem por qualidade e descarte de
# leituras curtas, conforme diretrizes de validação (seção 4.5).
#
# Uso:
#   bash scripts/pipeline/qc_fastp.sh <SAMPLE> [THREADS]
#   R1=/caminho/r1.fastq.gz R2=/caminho/r2.fastq.gz bash scripts/pipeline/qc_fastp.sh SAMPLE
#
# Variáveis de ambiente aceitas:
#   R1, R2          — caminhos dos reads (sobrescrevem busca automática em RAW_DIR)
#   SAMPLE_R1/R2    — idem (alias do pipeline)
#   SINGLE/SAMPLE_SINGLE — read single-end
#   THREADS         — número de threads (padrão: 4)
#   QC_MIN_LEN      — tamanho mínimo de leitura após trim (padrão: 20)
#   QC_MIN_QUAL     — Phred que define uma base qualificada no fastp (padrão: 20)
#   QC_OUT_DIR      — diretório de saída (padrão: data/cleaned)
#   QC_REPORT_DIR   — diretório dos relatórios (padrão: results/qc)
#
# Saída:
#   data/cleaned/{SAMPLE}_R1.clean.fastq.gz
#   data/cleaned/{SAMPLE}_R2.clean.fastq.gz
#   results/qc/{SAMPLE}_fastp.html
#   results/qc/{SAMPLE}_fastp.json
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
LEGACY_CONFIG="${REPO_ROOT}/config.env"

if [[ "${PIPELINE_CONFIG_LOADED:-0}" != "1" ]]; then
  if [[ -f "${CONFIG_FILE}" ]]; then
    # User config/generated metadata is resolved at runtime.
    # shellcheck disable=SC1090
    source "${CONFIG_FILE}"
  fi
fi

source "${SCRIPTS_ROOT}/lib/common.sh"

SAMPLE="${1:?SAMPLE obrigatório}"
THREADS="${2:-${THREADS:-4}}"
SAMPLE="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE")"

RAW_DIR="$(resolve_path "${RAW_DIR:-data/raw}")"
QC_OUT_DIR="$(resolve_path "${QC_OUT_DIR:-data/cleaned}")"
QC_REPORT_DIR="$(resolve_path "${QC_REPORT_DIR:-results/qc}")"

QC_MIN_LEN="${QC_MIN_LEN:-20}"
QC_MIN_QUAL="${QC_MIN_QUAL:-20}"
QC_ADAPTER_R1="${QC_ADAPTER_R1:-}"
QC_ADAPTER_R2="${QC_ADAPTER_R2:-}"
for adapter_sequence in "$QC_ADAPTER_R1" "$QC_ADAPTER_R2"; do
  [[ -z "$adapter_sequence" || "$adapter_sequence" =~ ^[ACGTNacgtn]+$ ]] || \
    log_error "Adaptadores de QC devem conter somente A/C/G/T/N."
done
[[ "$THREADS" =~ ^[1-9][0-9]*$ ]] || log_error "THREADS deve ser inteiro positivo."
[[ "$QC_MIN_LEN" =~ ^[1-9][0-9]*$ ]] || log_error "QC_MIN_LEN deve ser inteiro positivo."
if [[ ! "$QC_MIN_QUAL" =~ ^[0-9]+$ ]] || (( QC_MIN_QUAL > 93 )); then
  log_error "QC_MIN_QUAL deve ser inteiro entre 0 e 93."
fi

# ── Detecção de reads ────────────────────────────────────────────────────────
RAW_SINGLE="${SAMPLE_SINGLE:-${SINGLE:-}}"
RAW1="${SAMPLE_R1:-${R1:-}}"
RAW2="${SAMPLE_R2:-${R2:-}}"
if [[ -n "$RAW_SINGLE" && ( -n "$RAW1" || -n "$RAW2" ) ]]; then
  log_error "Use SAMPLE_SINGLE/SINGLE ou SAMPLE_R1/SAMPLE_R2, mas não ambos."
fi
if [[ -z "$RAW_SINGLE" && ( -n "$RAW1" || -n "$RAW2" ) && ( -z "$RAW1" || -z "$RAW2" ) ]]; then
  log_error "Entradas pareadas explícitas exigem SAMPLE_R1/R1 e SAMPLE_R2/R2."
fi
if [[ -n "$RAW_SINGLE" ]]; then
  RAW_SINGLE="$(resolve_path "$RAW_SINGLE")"
  check_file "$RAW_SINGLE"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$RAW_SINGLE" >/dev/null
else
  RAW1="${RAW1:-${RAW_DIR}/${SAMPLE}_R1.fastq.gz}"
  RAW2="${RAW2:-${RAW_DIR}/${SAMPLE}_R2.fastq.gz}"
  RAW1="$(resolve_path "$RAW1")"
  RAW2="$(resolve_path "$RAW2")"
  check_file "$RAW1"
  check_file "$RAW2"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$RAW1" --mate "$RAW2" >/dev/null
fi

# ── Verificar se fastp está disponível ──────────────────────────────────────
if ! command -v fastp >/dev/null 2>&1; then
  log_error $'fastp não encontrado no PATH.\nInstale com: sudo apt install -y fastp\nOu: conda install -c bioconda fastp'
fi

mkdir -p "$QC_OUT_DIR" "$QC_REPORT_DIR"

OUT_R1="${QC_OUT_DIR}/${SAMPLE}_R1.clean.fastq.gz"
OUT_R2="${QC_OUT_DIR}/${SAMPLE}_R2.clean.fastq.gz"
OUT_SINGLE="${QC_OUT_DIR}/${SAMPLE}.clean.fastq.gz"
HTML_REPORT="${QC_REPORT_DIR}/${SAMPLE}_fastp.html"
JSON_REPORT="${QC_REPORT_DIR}/${SAMPLE}_fastp.json"
WORK_DIR="$(mktemp -d "${QC_OUT_DIR}/.${SAMPLE}.fastp.XXXXXX")"
trap 'rm -rf -- "$WORK_DIR"' EXIT

promote_qc_outputs() {
  (( $# > 0 && $# % 2 == 0 )) || log_error "Erro interno na promoção dos artefatos de QC."
  local -a staged=() targets=() backups=() had_backup=() promoted=()
  local source target backup
  local i j

  while (( $# > 0 )); do
    staged+=("$1")
    targets+=("$2")
    shift 2
  done
  for source in "${staged[@]}"; do
    [[ -s "$source" ]] || log_error "Artefato de QC ausente ou vazio antes da promoção: ${source}"
  done

  for ((i = 0; i < ${#targets[@]}; i++)); do
    target="${targets[$i]}"
    backup="${WORK_DIR}/previous.${i}"
    backups+=("$backup")
    had_backup+=(0)
    if [[ -e "$target" ]]; then
      if ! mv "$target" "$backup"; then
        for ((j = 0; j < i; j++)); do
          if [[ "${had_backup[$j]}" == "1" ]]; then
            mv "${backups[$j]}" "${targets[$j]}" || true
          fi
        done
        log_error "Falha ao preservar artefatos de QC anteriores."
      fi
      had_backup[i]=1
    fi
  done

  for ((i = 0; i < ${#staged[@]}; i++)); do
    promoted+=(0)
    if mv "${staged[$i]}" "${targets[$i]}"; then
      promoted[i]=1
      continue
    fi
    for ((j = 0; j < ${#targets[@]}; j++)); do
      if [[ "${promoted[$j]:-0}" == "1" ]]; then
        rm -f -- "${targets[$j]}"
      fi
      if [[ "${had_backup[$j]}" == "1" ]]; then
        mv "${backups[$j]}" "${targets[$j]}" || true
      fi
    done
    log_error "Falha ao promover artefatos de QC; as saídas anteriores foram restauradas."
  done
}

log_info "[fastp] sample=${SAMPLE}  threads=${THREADS}"
log_info "[fastp] min_len=${QC_MIN_LEN}  qualified_quality_phred=${QC_MIN_QUAL}"

FASTP_COMMON=(
  --html "$WORK_DIR/fastp.html"
  --json "$WORK_DIR/fastp.json"
  --thread "$THREADS"
  --qualified_quality_phred "$QC_MIN_QUAL"
  --length_required "$QC_MIN_LEN"
  --overrepresentation_analysis
)
[[ -z "$QC_ADAPTER_R1" ]] || FASTP_COMMON+=(--adapter_sequence "$QC_ADAPTER_R1")
[[ -z "$QC_ADAPTER_R2" ]] || FASTP_COMMON+=(--adapter_sequence_r2 "$QC_ADAPTER_R2")

if [[ -n "$RAW_SINGLE" ]]; then
  log_info "[fastp] entrada single-end: ${RAW_SINGLE}"
  fastp --in1 "$RAW_SINGLE" --out1 "$WORK_DIR/single.fastq.gz" "${FASTP_COMMON[@]}"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$WORK_DIR/single.fastq.gz" >/dev/null
  [[ -s "$WORK_DIR/fastp.html" ]] || log_error "fastp não gerou relatório HTML válido."
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastp-json "$WORK_DIR/fastp.json" >/dev/null
  promote_qc_outputs \
    "$WORK_DIR/single.fastq.gz" "$OUT_SINGLE" \
    "$WORK_DIR/fastp.html" "$HTML_REPORT" \
    "$WORK_DIR/fastp.json" "$JSON_REPORT"
  log_info "[fastp] OK: read single-end limpa em ${OUT_SINGLE}"
  echo "[QC_SINGLE_CLEAN]=${OUT_SINGLE}"
else
  log_info "[fastp] entrada pareada: ${RAW1}"
  log_info "[fastp]                   ${RAW2}"
  fastp \
    --in1 "$RAW1" --in2 "$RAW2" \
    --out1 "$WORK_DIR/R1.fastq.gz" --out2 "$WORK_DIR/R2.fastq.gz" \
    --detect_adapter_for_pe --correction --overlap_len_require 30 \
    "${FASTP_COMMON[@]}"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$WORK_DIR/R1.fastq.gz" \
    --mate "$WORK_DIR/R2.fastq.gz" >/dev/null
  [[ -s "$WORK_DIR/fastp.html" ]] || log_error "fastp não gerou relatório HTML válido."
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastp-json "$WORK_DIR/fastp.json" >/dev/null
  promote_qc_outputs \
    "$WORK_DIR/R1.fastq.gz" "$OUT_R1" \
    "$WORK_DIR/R2.fastq.gz" "$OUT_R2" \
    "$WORK_DIR/fastp.html" "$HTML_REPORT" \
    "$WORK_DIR/fastp.json" "$JSON_REPORT"
  log_info "[fastp] OK: reads limpas em ${OUT_R1} e ${OUT_R2}"
  echo "[QC_R1_CLEAN]=${OUT_R1}"
  echo "[QC_R2_CLEAN]=${OUT_R2}"
fi
