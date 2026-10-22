#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Used by sourced genein_config_path.sh/common.sh for config and path resolution.
# shellcheck disable=SC2034
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

source "${SCRIPTS_ROOT}/lib/common.sh"

usage() {
  cat <<'USAGE'
Uso: scripts/ops/stage_sample.sh --id <ID> [--r1 <path> --r2 <path>] [--single <path>] [--copy]

Opções:
  --id <ID>        identificador da amostra (obrigatório)
  --r1 <path>      leitura R1 (pareado)
  --r2 <path>      leitura R2 (opcional)
  --single <path>  leitura single-end (não usar com --r1/--r2)
  --copy           copia arquivos (padrão: symlink)

Saída:
  data/raw/<ID>_R1.fastq.gz e data/raw/<ID>_R2.fastq.gz (pareado)
  data/raw/<ID>.fastq.gz (single-end)
USAGE
}

ID=""
R1=""
R2=""
SINGLE=""
USE_COPY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id)
      ID="${2:-}"
      shift 2
      ;;
    --r1)
      R1="${2:-}"
      shift 2
      ;;
    --r2)
      R2="${2:-}"
      shift 2
      ;;
    --single)
      SINGLE="${2:-}"
      shift 2
      ;;
    --copy)
      USE_COPY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$ID" ]]; then
  log_error "--id é obrigatório."
fi

ID="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$ID")"

if [[ -z "$SINGLE" && ( -z "$R1" || -z "$R2" ) ]]; then
  log_error "paired input requires both R1 and R2"
fi

if [[ -n "$SINGLE" && ( -n "$R1" || -n "$R2" ) ]]; then
  log_error "Use --single ou --r1/--r2, mas não ambos."
fi

if [[ -z "$SINGLE" && -z "$R1" ]]; then
  log_error "Informe --r1/--r2 ou --single."
fi

RAW_DIR="$(resolve_path "${RAW_DIR:-data/raw}")"
mkdir -p "$RAW_DIR"

stage_file() {
  local src="$1"
  local dest="$2"
  local tmp="${dest}.tmp.$$"
  rm -f "$tmp"
  if [[ ! -f "$src" ]]; then
    log_error "Arquivo não encontrado: $src"
  fi
  if [[ "$src" == *.gz ]]; then
    if [[ $USE_COPY -eq 1 ]]; then
      cp -f "$src" "$tmp"
    else
      ln -sf "$src" "$tmp"
    fi
  else
    gzip -c "$src" > "$tmp"
  fi
  mv -f "$tmp" "$dest"
}

if [[ -n "$SINGLE" ]]; then
  SINGLE="$(resolve_path "$SINGLE")"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$SINGLE"
  OUT_SINGLE="${RAW_DIR}/${ID}.fastq.gz"
  log_info "Staging single-end para ${OUT_SINGLE}"
  stage_file "$SINGLE" "$OUT_SINGLE"
  exit 0
fi

R1="$(resolve_path "$R1")"
R2="$(resolve_path "$R2")"
python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$R1" --mate "$R2"
OUT_R1="${RAW_DIR}/${ID}_R1.fastq.gz"
log_info "Staging R1 para ${OUT_R1}"
stage_file "$R1" "$OUT_R1"

if [[ -n "$R2" ]]; then
  OUT_R2="${RAW_DIR}/${ID}_R2.fastq.gz"
  log_info "Staging R2 para ${OUT_R2}"
  stage_file "$R2" "$OUT_R2"
else
  log_warn "R2 não informado. Apenas ${OUT_R1} foi gerado."
fi
