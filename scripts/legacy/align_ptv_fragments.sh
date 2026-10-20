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

# Arquivos de entrada/saída
REF_FA="${REF_FA:-${REF_FASTA:-${REPO_ROOT}/data/ptv_db.fa}}"
# (legado) se existir data/ref/ptv_db.fa, prefira
if [[ -z "${REF_FASTA:-}" && -e "data/ref/ptv_db.fa" ]]; then REF_FA="data/ref/ptv_db.fa"; fi
WORK_DIR="${LEGACY_WORK_DIR:-${REPO_ROOT}/run_T1/work}"
FRAG_FA="${WORK_DIR}/ptv_hits_fragments.fa"
MERGED_FA="${WORK_DIR}/ptv_fragments_plus_ref.fa"
ALN_FA="${WORK_DIR}/ptv_fragments_plus_ref.aln.fa"
mkdir -p "$WORK_DIR"

echo "=== Alinhamento PTV: referências + fragmentos ==="

# checagens básicas
check_file "$REF_FA"
check_file "$FRAG_FA"

command -v mafft >/dev/null 2>&1 || log_error "'mafft' não encontrado no PATH. Instale o MAFFT antes de rodar este script."

log_info "[1/2] Concatenando referências e fragmentos em: $MERGED_FA"
cat "$REF_FA" "$FRAG_FA" > "$MERGED_FA"

log_info "[2/2] Rodando MAFFT (modo automático)..."
mafft --auto "$MERGED_FA" > "$ALN_FA"

echo
log_info "[OK] Alinhamento pronto em: $ALN_FA"
