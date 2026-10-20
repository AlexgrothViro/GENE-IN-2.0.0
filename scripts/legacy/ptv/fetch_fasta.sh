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

if [[ $# -ne 1 ]]; then
  log_error "Uso: $0 <saida_fasta> (ex.: data/ref/ptv_db.fa)"
fi

OUT_FASTA="$1"
OUT_DIR="$(dirname "$OUT_FASTA")"

if [[ -s "$OUT_FASTA" ]]; then
  log_info "FASTA já existe e não está vazio: $OUT_FASTA"
  exit 0
fi

mkdir -p "$OUT_DIR"

QUERY='"Teschovirus"[Organism]'

have_edirect() {
  command -v esearch >/dev/null 2>&1 && command -v efetch >/dev/null 2>&1
}

if ! have_edirect; then
  cat >&2 <<'EOF'
ERRO: EDirect (esearch/efetch) não encontrado no PATH.
`esearch` e `efetch` fazem parte do pacote EDirect.
No Ubuntu/WSL, instale com:
  sudo apt update && sudo apt install -y ncbi-entrez-direct
Alternativa sem download NCBI: forneça um FASTA local em:
  data/ref/ptv.fa
(compat legado também aceito em: data/ref/ptv_db.fa)
EOF
  exit 1
fi

log_info "Baixando sequências de Teschovirus do NCBI (QUERY=${QUERY})..."
esearch -db nucleotide -query "$QUERY" | efetch -format fasta > "$OUT_FASTA"

if [[ ! -s "$OUT_FASTA" ]]; then
  log_error "download falhou, $OUT_FASTA está vazio."
fi

log_info "FASTA salvo em $OUT_FASTA"
