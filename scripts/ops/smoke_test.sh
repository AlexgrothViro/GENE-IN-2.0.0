#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
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

DB="${DB:-ptv}"
DB_QUERY="${DB_QUERY:-\"Teschovirus\"[Organism]}"
REF_FASTA="${REF_FASTA:-data/ref/${DB}.fa}"
BLAST_DB="${BLAST_DB:-blastdb/${DB}}"
BOWTIE2_INDEX="${BOWTIE2_INDEX:-bowtie2/${DB}}"

echo "== Smoke test do pipeline =="

log_info "Preparando DB (DB=${DB})..."
make -C "$REPO_ROOT" db DB="$DB" DB_QUERY="$DB_QUERY" REF_FASTA="$REF_FASTA" \
  BLAST_DB="$BLAST_DB" BOWTIE2_INDEX="$BOWTIE2_INDEX"

check_file "$REF_FASTA"
log_info "FASTA presente: $REF_FASTA"

missing_db=0
for ext in nhr nin nsq; do
  f="${BLAST_DB}.${ext}"
  if [[ ! -f "$f" ]]; then
    log_warn "arquivo BLAST DB faltando: $f"
    missing_db=1
  fi
done
if [[ $missing_db -ne 0 ]]; then
  log_error "Sugestão: make db DB=${DB}"
fi
log_info "Banco BLAST encontrado em prefixo: $BLAST_DB"

missing_bt2=0
for f in "${BOWTIE2_INDEX}".*.bt2*; do
  if [[ ! -e "$f" ]]; then
    missing_bt2=1
  fi
done
if [[ $missing_bt2 -ne 0 ]]; then
  log_error "índice Bowtie2 ausente para prefixo ${BOWTIE2_INDEX}. Sugestão: make db DB=${DB}"
fi
log_info "Índice Bowtie2 encontrado em prefixo: $BOWTIE2_INDEX"

echo "[Teste rápido] blastn (entrada curta via stdin, sem esperar hits)..."
printf ">q1\nACTGACTGACTG\n" | blastn -query - -db "$BLAST_DB" -outfmt 6 >/dev/null
log_info "blastn executou."

echo "=== Checagem de sintaxe dos scripts críticos ==="
SYNTAX_OK=1
for script in \
  scripts/pipeline/run.sh \
  scripts/pipeline/assemblers/spades.sh \
  scripts/pipeline/assemblers/metaspades.sh \
  scripts/pipeline/assemblers/velvet.sh \
  scripts/pipeline/qc_fastp.sh \
  scripts/pipeline/filter_host.sh \
  scripts/pipeline/report_minimal.sh; do
  if [[ -f "${REPO_ROOT}/${script}" ]]; then
    if bash -n "${REPO_ROOT}/${script}" 2>&1; then
      log_info "Sintaxe OK: ${script}"
    else
      log_warn "Sintaxe FALHOU: ${script}"
      SYNTAX_OK=0
    fi
  fi
done
if [[ $SYNTAX_OK -eq 0 ]]; then
  log_error "Um ou mais scripts têm erros de sintaxe. Corrija antes de rodar o pipeline."
fi
log_info "Checagem de sintaxe concluída."

log_info "Smoke test concluído com sucesso."
