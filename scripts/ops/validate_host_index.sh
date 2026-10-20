#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# resolve_path in common.sh consumes this root for relative index paths.
# shellcheck disable=SC2034
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

source "${SCRIPTS_ROOT}/lib/common.sh"
source "${SCRIPTS_ROOT}/lib/host_filter.sh"

if [[ $# -lt 1 || -z "${1:-}" ]]; then
  log_error "Uso: $0 PREFIXO_INDICE_BOWTIE2"
fi

HOST_INDEX_PREFIX="$(resolve_path "$1")"
INDEX_KIND="$(validate_bt2_index "$HOST_INDEX_PREFIX")"

echo "OK: indice Bowtie2 ${INDEX_KIND} valido em ${HOST_INDEX_PREFIX}"
