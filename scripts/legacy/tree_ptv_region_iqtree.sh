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
ALN_FA="${1:-${WORK_DIR}/ptv_region_KX686489_1_7209.aln.fa}"
PREFIX="${2:-${WORK_DIR}/ptv_region_KX686489_1_7209.iqtree}"

echo "=== Árvore PTV (região KX686489.1:1-7192) com IQ-TREE ==="

check_file "$ALN_FA"

IQBIN=""

if command -v iqtree2 >/dev/null 2>&1; then
  IQBIN="iqtree2"
elif command -v iqtree >/dev/null 2>&1; then
  IQBIN="iqtree"
else
  log_error "IQ-TREE não encontrado (nem 'iqtree2' nem 'iqtree' no PATH). Instale, por exemplo, com: sudo apt update && sudo apt install iqtree"
fi

log_info "Usando binário: $IQBIN"

"$IQBIN" -s "$ALN_FA" \
  -m GTR+G \
  -nt AUTO \
  -bb 1000 \
  -alrt 1000 \
  -pre "$PREFIX"

echo
log_info "IQ-TREE finalizado."
echo "Arquivos principais em:"
echo "  ${PREFIX}.treefile  (árvore principal)"
echo "  ${PREFIX}.log       (log da análise)"
echo "  ${PREFIX}.iqtree    (resumo do modelo e estatísticas)"
