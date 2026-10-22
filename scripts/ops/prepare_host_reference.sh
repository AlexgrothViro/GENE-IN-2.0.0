#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

INCOMING_HOST_ACCESSION="${HOST_ACCESSION:-}"
INCOMING_HOST_NAME="${HOST_NAME:-}"
INCOMING_HOST_INDEX_PREFIX="${HOST_INDEX_PREFIX:-}"
INCOMING_HOST_FASTA="${HOST_FASTA:-}"
INCOMING_HOST_RSYNC_URL="${HOST_RSYNC_URL:-}"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

if [[ -n "$INCOMING_HOST_ACCESSION" ]]; then
  HOST_ACCESSION="$INCOMING_HOST_ACCESSION"
fi
if [[ -n "$INCOMING_HOST_NAME" ]]; then
  HOST_NAME="$INCOMING_HOST_NAME"
fi
if [[ -n "$INCOMING_HOST_INDEX_PREFIX" ]]; then
  HOST_INDEX_PREFIX="$INCOMING_HOST_INDEX_PREFIX"
fi
if [[ -n "$INCOMING_HOST_FASTA" ]]; then
  HOST_FASTA="$INCOMING_HOST_FASTA"
fi
if [[ -n "$INCOMING_HOST_RSYNC_URL" ]]; then
  HOST_RSYNC_URL="$INCOMING_HOST_RSYNC_URL"
fi

source "${SCRIPTS_ROOT}/lib/common.sh"
source "${SCRIPTS_ROOT}/lib/host_filter.sh"

: "${HOST_ACCESSION:?Defina HOST_ACCESSION antes de chamar este script}"
HOST_NAME="${HOST_NAME:-hospedeiro}"

DEST_DIR="$(resolve_path "${DEST_DIR:-ref/host}")"
HOST_SLUG="$(printf '%s' "$HOST_NAME" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9_.-')"
HOST_SLUG="${HOST_SLUG:-host}"
FA="$(resolve_path "${HOST_FASTA:-${DEST_DIR}/${HOST_SLUG}.fa}")"
HOST_INDEX_PREFIX="$(resolve_path "${HOST_INDEX_PREFIX:-${DEST_DIR}/${HOST_SLUG}_bt2}")"
LOG_DIR="${REPO_ROOT}/logs/ref"
BUILD_STDOUT="${LOG_DIR}/${HOST_SLUG}_bowtie2_build.stdout.log"
BUILD_STDERR="${LOG_DIR}/${HOST_SLUG}_bowtie2_build.stderr.log"

DEFAULT_SUS_SCROFA_RSYNC_URL="rsync://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/003/025/GCF_000003025.6_Sscrofa11.1/"
RSYNC_URL="${HOST_RSYNC_URL:-${SUS_SCROFA_RSYNC_URL:-}}"
if [[ -z "$RSYNC_URL" && "$HOST_ACCESSION" == "GCF_000003025.6" ]]; then
  RSYNC_URL="$DEFAULT_SUS_SCROFA_RSYNC_URL"
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

validate_md5_manifest() {
  local manifest="$1"
  local manifest_dir
  manifest_dir="$(dirname "$manifest")"
  (cd "$manifest_dir" && md5sum -c "$(basename "$manifest")")
}

find_genome_fasta() {
  local root="$1"
  find "$root" -type f \( -name "*genomic.fna" -o -name "*genomic.fna.gz" -o -name "*.fna" -o -name "*.fa" -o -name "*.fasta" \) \
    | sort \
    | head -n 1
}

install_fasta() {
  local src="$1"
  mkdir -p "$(dirname "$FA")"
  if [[ "$src" == *.gz ]]; then
    gzip -cd "$src" > "$FA"
  else
    cp -f "$src" "$FA"
  fi
  if [[ ! -s "$FA" ]]; then
    log_error "arquivo FASTA ${FA} esta vazio apos a instalacao."
  fi
  if ! grep -q '^>' "$FA"; then
    log_error "arquivo FASTA ${FA} nao possui cabecalhos FASTA validos."
  fi
}

download_with_datasets() {
  if ! command -v unzip >/dev/null 2>&1; then
    log_error "unzip nao encontrado. Instale unzip ou atualize o ambiente Gene-In antes de baixar o genoma."
  fi

  local zip_file="${TMP_DIR}/host_dataset.zip"
  log_info "Baixando genoma do hospedeiro '${HOST_NAME}' via NCBI Datasets (${HOST_ACCESSION})..."
  if ! datasets download genome accession "$HOST_ACCESSION" --include genome --filename "$zip_file"; then
    log_error "falha no download do genoma do hospedeiro '${HOST_NAME}' via NCBI Datasets (${HOST_ACCESSION})."
  fi
  if ! unzip -q "$zip_file" -d "${TMP_DIR}/datasets"; then
    log_error "falha ao extrair pacote NCBI Datasets: ${zip_file}"
  fi

  local manifest
  manifest="$(find "${TMP_DIR}/datasets" -type f -name 'md5sum.txt' | head -n 1)"
  if [[ -z "$manifest" ]]; then
    log_error "manifesto md5sum.txt nao encontrado no pacote NCBI Datasets."
  fi
  if ! validate_md5_manifest "$manifest"; then
    log_error "falha na validacao MD5 do pacote NCBI Datasets."
  fi

  local fasta
  fasta="$(find_genome_fasta "${TMP_DIR}/datasets")"
  if [[ -z "$fasta" ]]; then
    log_error "FASTA genomico nao encontrado no pacote NCBI Datasets."
  fi
  install_fasta "$fasta"
}

download_with_rsync() {
  if [[ -z "$RSYNC_URL" ]]; then
    log_error "datasets nao encontrado e HOST_RSYNC_URL nao foi definido para fallback rsync."
  fi
  if ! command -v rsync >/dev/null 2>&1; then
    log_error "datasets nao encontrado e rsync tambem nao esta disponivel para fallback."
  fi

  log_info "Baixando genoma do hospedeiro '${HOST_NAME}' via rsync com retomada parcial..."
  mkdir -p "${TMP_DIR}/rsync"
  if ! rsync -av --partial "$RSYNC_URL" "${TMP_DIR}/rsync/"; then
    log_error "falha no download rsync do genoma do hospedeiro '${HOST_NAME}': ${RSYNC_URL}"
  fi

  local manifest
  manifest="$(find "${TMP_DIR}/rsync" -type f -name 'md5checksums.txt' | head -n 1)"
  if [[ -z "$manifest" ]]; then
    log_error "md5checksums.txt nao encontrado no diretorio rsync do NCBI."
  fi
  if ! validate_md5_manifest "$manifest"; then
    log_error "falha na validacao MD5 do download rsync."
  fi

  local fasta
  fasta="$(find_genome_fasta "${TMP_DIR}/rsync")"
  if [[ -z "$fasta" ]]; then
    log_error "FASTA genomico nao encontrado no download rsync."
  fi
  install_fasta "$fasta"
}

build_bowtie_index() {
  local rebuild="${HOST_REBUILD_INDEX:-false}"
  if [[ "$rebuild" != "true" ]] && validate_bt2_index "$HOST_INDEX_PREFIX" >/dev/null 2>&1; then
    log_info "Indice Bowtie2 ja existe e esta valido: ${HOST_INDEX_PREFIX}"
    return 0
  fi

  if ! command -v bowtie2-build >/dev/null 2>&1; then
    log_error "bowtie2-build nao encontrado. Atualize o ambiente Gene-In antes de construir o indice."
  fi

  mkdir -p "$(dirname "$HOST_INDEX_PREFIX")" "$LOG_DIR"
  log_info "Construindo indice Bowtie2 para '${HOST_NAME}' em: ${HOST_INDEX_PREFIX}"
  if ! bowtie2-build "$FA" "$HOST_INDEX_PREFIX" > "$BUILD_STDOUT" 2> "$BUILD_STDERR"; then
    log_error "bowtie2-build falhou. Logs: stdout=${BUILD_STDOUT}; stderr=${BUILD_STDERR}"
  fi

  if ! validate_bt2_index "$HOST_INDEX_PREFIX" >/dev/null; then
    log_error "indice Bowtie2 foi construido, mas falhou na validacao: ${HOST_INDEX_PREFIX}"
  fi
}

echo "============================================="
echo "  Preparo da referencia de hospedeiro"
echo "  Fonte primaria: NCBI Datasets"
echo "  Fallback: rsync NCBI com checksum"
echo "============================================="
echo "Hospedeiro: ${HOST_NAME}"
echo "Accession: ${HOST_ACCESSION}"
echo "FASTA: ${FA}"
echo "Indice Bowtie2: ${HOST_INDEX_PREFIX}"
echo

if [[ -s "$FA" ]]; then
  log_info "FASTA existente encontrado: ${FA}"
else
  if command -v datasets >/dev/null 2>&1; then
    download_with_datasets
  else
    download_with_rsync
  fi
fi

seq_count="$(grep -c '^>' "$FA")"
log_info "Referencia do hospedeiro '${HOST_NAME}' salva em: ${FA}"
log_info "Sequencias FASTA detectadas: ${seq_count}"

build_bowtie_index
log_info "Referencia de hospedeiro pronta: ${HOST_INDEX_PREFIX}"
