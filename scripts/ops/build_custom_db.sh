#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
LEGACY_CONFIG="${REPO_ROOT}/config.env"
if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/common.sh"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  log_error "picornavirus.env não encontrado em ${CONFIG_FILE}. Copie config/picornavirus.env.example para o diretório de trabalho."
fi

command -v esearch >/dev/null 2>&1 || log_error "EDirect não encontrado (esearch). Instale EDirect."
command -v efetch  >/dev/null 2>&1 || log_error "EDirect não encontrado (efetch). Instale EDirect."
command -v makeblastdb >/dev/null 2>&1 || log_error "makeblastdb não encontrado (blast+)."

DB_ROOT_RESOLVED="$(resolve_path "${DB_ROOT:-data/db}")"
DB_DIR="${DB_ROOT_RESOLVED}/${DB_NAME}"
FASTA="${DB_DIR}/${DB_NAME}.fasta"
BLASTDB="${DB_DIR}/${DB_NAME}"

mkdir -p "$DB_DIR"

QUERY="${NCBI_QUERY:-txid${TARGET_TAXID}[Organism:exp] AND refseq[filter]}"
RETMAX="${EDIRECT_RETMAX:-500}"

log_info "[DB] Query: $QUERY"
log_info "[DB] retmax: $RETMAX"
log_info "[DB] Baixando FASTA..."

FASTA_TMP="${FASTA}.download.$$"
trap 'rm -f "$FASTA_TMP"' EXIT
if ! fetch_ncbi_fasta "$FASTA_TMP" nucleotide "$QUERY" "$RETMAX"; then
  log_error "Download NCBI falhou apos ${EDIRECT_RETRIES:-3} tentativa(s); o FASTA existente nao foi substituido. Revise a conectividade TLS e a query."
fi
python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$FASTA_TMP"
mv -f "$FASTA_TMP" "$FASTA"

log_info "[DB] Sequências baixadas: $(grep -c '^>' "$FASTA" || true)"
log_info "[DB] Construindo BLAST DB..."
makeblastdb -in "$FASTA" -dbtype nucl -out "$BLASTDB" -parse_seqids

log_info "[DB] OK: $BLASTDB"
