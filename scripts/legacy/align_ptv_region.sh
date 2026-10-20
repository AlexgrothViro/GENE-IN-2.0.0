#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

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

source "${REPO_ROOT}/scripts/lib/common.sh"

WORK_DIR="${LEGACY_WORK_DIR:-${REPO_ROOT}/run_T1/work}"
IN_FA="${1:-${WORK_DIR}/ptv_region_KX686489_1_7209.fa}"
OUT_FA="${2:-${WORK_DIR}/ptv_region_KX686489_1_7209.aln.fa}"
mkdir -p "$(dirname "$OUT_FA")"

log_info "=== Alinhando região PTV com MAFFT ==="
log_info "FASTA de entrada: $IN_FA"
log_info "Saída de alinhamento: $OUT_FA"

check_file "$IN_FA"

command -v mafft >/dev/null 2>&1 || log_error "'mafft' não encontrado no PATH. Instale o MAFFT antes de rodar este script."

mafft --auto "$IN_FA" > "$OUT_FA"

log_info "Alinhamento escrito em: $OUT_FA"
