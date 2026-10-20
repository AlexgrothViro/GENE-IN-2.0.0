#!/usr/bin/env bash
set -euo pipefail

# ── Funções padronizadas de log ──────────────────────────────────────────────
# Formato: [NÍVEL] [ETAPA] [AMOSTRA] — descrição — ação sugerida
#
# Identificadores de etapa (sem acento):
#   QC_PREFLIGHT, DATABASE_PREFLIGHT, QC_FASTP, HOST_FILTER, ASSEMBLY, RESCUE_READS,
#   BLAST, CLASSIFICACAO, REPORT, DASHBOARD
#
# Níveis: FATAL (interrompe), RECUPERADO (fallback), AVISO (não fatal), INFO

log_context()   { printf '%s' "${PIPELINE_ETAPA:+[${PIPELINE_ETAPA}] }${SAMPLE_NAME:+[${SAMPLE_NAME}]}"; }
log_fatal()     { echo "[FATAL]      $(log_context) — $*" >&2; exit 1; }
log_recovered() { echo "[RECUPERADO] $(log_context) — $*"; }
log_warning()   { echo "[AVISO]      $(log_context) — $*" >&2; }
log_info()      { echo "[INFO]       $(log_context) — $*"; }

# Aliases para compatibilidade com código existente (run_assembly_router.sh, etc.)
log_error() { log_fatal "$@"; }
log_warn()  { log_warning "$@"; }

resolve_path() {
  local path="$1"
  if [[ "$path" == /* ]]; then
    echo "$path"
  else
    echo "${REPO_ROOT}/${path}"
  fi
}

check_file() {
  if [[ ! -s "$1" ]]; then
    log_error "Arquivo não encontrado ou vazio: $1"
  fi
}

# BLAST+'s own -db argument parser reads its value as a whitespace-separated
# list of database names, so a single path containing spaces is otherwise
# misread as multiple databases. Wrapping the value in embedded literal
# quotes (part of the string BLAST+ receives, not shell quoting, which
# already preserves the path intact) makes it keep the whole path as one
# database name.
blast_db_arg() {
  local database="$1"
  if [[ "$database" == *[[:space:]]* ]]; then
    printf '"%s"' "$database"
  else
    printf '%s' "$database"
  fi
}

# Validate the database through the BLAST+ public interface instead of
# assuming a particular on-disk layout. This accepts both traditional
# single-volume databases and v5 aliases promoted to immutable generations.
validate_blast_database() {
  local database="$1"
  command -v blastdbcmd >/dev/null 2>&1 || return 127
  blastdbcmd -db "$(blast_db_arg "$database")" -info >/dev/null 2>&1
}

check_blast_database() {
  local database="$1"
  command -v blastdbcmd >/dev/null 2>&1 || \
    log_error "blastdbcmd não encontrado no PATH; instale BLAST+ antes de validar o banco."
  validate_blast_database "$database" || \
    log_error "Banco BLAST ausente, incompleto ou ilegível no prefixo: $database"
}

# Download via EDirect with bounded retries. The caller must validate the
# temporary FASTA before promoting it to the canonical cache.
fetch_ncbi_fasta() {
  local output="$1"
  local ncbi_db="$2"
  local query="$3"
  local retmax="${4:-}"
  local retries="${EDIRECT_RETRIES:-3}"
  local delay="${EDIRECT_RETRY_DELAY:-5}"
  local attempt status error_log

  [[ "$retries" =~ ^[1-9][0-9]*$ ]] || log_error "EDIRECT_RETRIES invalido: $retries (use um inteiro >= 1)"
  [[ "$delay" =~ ^[0-9]+$ ]] || log_error "EDIRECT_RETRY_DELAY invalido: $delay (use segundos inteiros >= 0)"

  rm -f "$output"
  error_log="${output}.edirect.stderr.$$"
  rm -f "$error_log"
  for ((attempt = 1; attempt <= retries; attempt++)); do
    rm -f "$output"
    log_info "EDirect tentativa ${attempt}/${retries} (db=${ncbi_db})..."
    if [[ -n "$retmax" ]]; then
      if esearch -db "$ncbi_db" -query "$query" -retmax "$retmax" 2>"$error_log" | \
          efetch -format fasta >> "$output" 2>>"$error_log"; then
        status=0
      else
        status=$?
      fi
    else
      if esearch -db "$ncbi_db" -query "$query" 2>"$error_log" | \
          efetch -format fasta >> "$output" 2>>"$error_log"; then
        status=0
      else
        status=$?
      fi
    fi
    if [[ "$status" -eq 0 && -s "$output" ]] && grep -q '^>' "$output"; then
      rm -f "$error_log"
      return 0
    fi
    rm -f "$output"
    if [[ -s "$error_log" ]]; then
      log_warning "EDirect falhou (status=${status}); detalhe: $(tail -n 1 "$error_log")"
    else
      log_warning "EDirect retornou FASTA vazio ou invalido (status=${status})."
    fi
    if (( attempt < retries )); then
      log_info "Aguardando ${delay}s antes de repetir o download..."
      sleep "$delay"
    fi
  done
  rm -f "$error_log"
  return 1
}
