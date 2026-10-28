#!/usr/bin/env bash
# Internal single-sample stages. Sourced after prepare_run.sh; never dispatches batches.
SAMPLE_NAME="${SAMPLE_OVERRIDE:-${SAMPLE_NAME:-${SAMPLE:-}}}"
if [[ -z "$SAMPLE_NAME" ]]; then
  echo "[FATAL] informe --sample NOME ou defina SAMPLE_ID/SAMPLE_NAME/SAMPLE explicitamente" >&2
  exit 2
fi
SAMPLE_NAME="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE_NAME")"
PIPELINE_SCRATCH="$(genein_scratch_dir)"
mkdir -p "${PIPELINE_SCRATCH}"
exec 8>"${PIPELINE_SCRATCH}/${SAMPLE_NAME}.pipeline.lock"
if ! flock -n 8; then
  echo "[FATAL] ja existe um pipeline em execucao para a amostra '${SAMPLE_NAME}'" >&2
  exit 1
fi
if [[ -n "$SAMPLE_OVERRIDE" ]]; then
  SAMPLE_ID="$SAMPLE_NAME"
else
  SAMPLE_ID="${SAMPLE_ID:-$SAMPLE_NAME}"
fi
# Path-safe version: espaços trocados por _ para caminhos de diretórios de montagem
# Um único resolvedor decide THREADS, VELVET_K, ASSEMBLER (inclusive a
# imposição do perfil assembly-consensus), BLAST_TASK/WORD_SIZE/EVALUE,
# HOST_FILTER_ENABLED, DB/DB_QUERY/BLAST_DB, todos os caminhos (resolve_path)
# e os campos Evidence 2.0 repassados ao scripts/evidence/run.sh — nas
# mesmas prioridades e com as mesmas validações que antes viviam espalhadas
# em ~100 linhas de bash. O shell só grava os overrides explícitos de CLI e
# lê de volta o JSON congelado.
RESOLVED_CONFIG_JSON="${PIPELINE_SCRATCH}/${SAMPLE_NAME}.resolved_config.json"
RESOLVE_CONFIG_CLI_ARGS=(
  --cli "SAMPLE_R1=${SAMPLE_R1_OVERRIDE}"
  --cli "SAMPLE_R2=${SAMPLE_R2_OVERRIDE}"
  --cli "SAMPLE_SINGLE=${SAMPLE_SINGLE_OVERRIDE}"
  --cli "ASSEMBLER=${ASSEMBLER_OVERRIDE}"
  --cli "ANALYSIS_PROFILE=${ANALYSIS_PROFILE_OVERRIDE}"
  --cli "VELVET_K=${KMER_OVERRIDE}"
  --cli "THREADS=${THREADS_OVERRIDE}"
  --cli "SPADES_PARAMS=${SPADES_PARAMS_OVERRIDE}"
  --cli "ADVANCED_KMERS=${ADVANCED_KMERS_OVERRIDE}"
  --cli "BLAST_TASK=${BLAST_TASK_OVERRIDE}"
  --cli "BLAST_WORD_SIZE=${BLAST_WORD_SIZE_OVERRIDE}"
  --cli "BLAST_EVALUE=${BLAST_EVALUE_OVERRIDE}"
  --cli "CONTIGS=${CONTIGS_OVERRIDE}"
  --cli "SEARCH_PROFILES=${SEARCH_PROFILES_OVERRIDE}"
  --cli "EVIDENCE_V2=${EVIDENCE_V2_OVERRIDE}"
  --cli "EVIDENCE_PROFILES=${EVIDENCE_PROFILES_OVERRIDE}"
  --cli "EVIDENCE_ROOT=${EVIDENCE_ROOT_OVERRIDE}"
)
# Explicit output isolation wins over any checkout config output directories.
if [[ -n "${GENEIN_WORK_ROOT:-}" ]]; then
  RESOLVE_CONFIG_CLI_ARGS+=(
    --cli "RAW_DIR=${WORK_ROOT}/data/raw"
    --cli "QC_OUT_DIR=${WORK_ROOT}/data/cleaned"
    --cli "QC_REPORT_DIR=${WORK_ROOT}/results/qc"
    --cli "HOST_REMOVED_DIR=${WORK_ROOT}/data/host_removed"
  )
  export ASSEMBLY_DIR="${WORK_ROOT}/data/assemblies"
fi
python3 "${SCRIPT_DIR}/resolve_config.py" pipeline \
  --repo-root "$REPO_ROOT" --sample-name "$SAMPLE_NAME" \
  --analysis-profiles-config "$ANALYSIS_PROFILES_CONFIG" \
  "${RESOLVE_CONFIG_INCOMING_ARGS[@]}" "${RESOLVE_CONFIG_SOURCED_ARGS[@]}" "${RESOLVE_CONFIG_CLI_ARGS[@]}" \
  --out "$RESOLVED_CONFIG_JSON"
eval "$(python3 "${SCRIPT_DIR}/resolve_config.py" emit-shell --in "$RESOLVED_CONFIG_JSON")"
# A identidade de DB só muda por ambiente/CLI (nunca pelo config file
# sozinho); quando isso ocorre, REF_FASTA/BOWTIE2_INDEX de um DB anterior
# ficam obsoletos e não devem sobreviver para os targets do Makefile.
if [[ "$DB_IDENTITY_OVERRIDDEN" == "true" ]]; then
  unset REF_FASTA BOWTIE2_INDEX
fi
if [[ $SKIP_ASSEMBLY -eq 1 && -z "$CONTIGS" ]]; then
  log_fatal "--skip-assembly exige --contigs <arquivo> — Forneca o arquivo de contigs."
fi

export HOST_INDEX_PREFIX HOST_NAME HOST_ACCESSION HOST_FILTER_ENABLED HOST_MIN_ALIGNMENT_RATE HOST_EXPECTED
export QC_MIN_LEN QC_MIN_QUAL THREADS
export QC_ADAPTER_R1 QC_ADAPTER_R2
# Define e exporta variáveis de contexto de log
export SAMPLE_NAME
export PIPELINE_ETAPA="QC_PREFLIGHT"
ASSEMBLER_LABEL="$ASSEMBLER"
[[ "$ASSEMBLER" != "consensus" ]] || ASSEMBLER_LABEL="MULTI — SPAdes, metaSPAdes e Velvet"

# ── Log por amostra ──────────────────────────────────────────────────────────
# Grava logs/{SAMPLE_NAME}_pipeline.log conforme documentado no README.
# Usa tee em modo append para preservar execuções anteriores.
# Compatível com pipefail: o processo principal continua sendo o pai.
LOG_DIR="${WORK_ROOT}/logs"
mkdir -p "$LOG_DIR"
PIPELINE_LOG="${LOG_DIR}/${SAMPLE_NAME}_pipeline.log"
exec > >(tee -a "$PIPELINE_LOG") 2>&1
echo "=== Pipeline iniciado em $(date -Iseconds) ==="
echo "    Amostra: ${SAMPLE_NAME}  Perfil: ${ANALYSIS_PROFILE}  Montador: ${ASSEMBLER_LABEL}  Banco: ${DB:-custom}"
echo "=============================================="

# Reject an unavailable host index before any FASTQ processing.
if [[ "$HOST_FILTER_ENABLED" == "true" && $SKIP_HOST_FILTER -eq 0 && "$INPUT_MODE" == "READS" ]]; then
  export PIPELINE_ETAPA="HOST_PREFLIGHT"
  [[ -n "$HOST_NAME" && -n "$HOST_INDEX_PREFIX" ]] || log_fatal "Informe nome e prefixo do índice do hospedeiro. Veja docs/HOSPEDEIRO_BETA.md."
  validate_bt2_index "$HOST_INDEX_PREFIX" >/dev/null || log_fatal "Índice do hospedeiro inválido em ${HOST_INDEX_PREFIX}. Prepare com bowtie2-build e informe o prefixo sem .1.bt2; veja docs/HOSPEDEIRO_BETA.md."
  export PIPELINE_ETAPA="QC_PREFLIGHT"
fi

export SAMPLE_ID SAMPLE_NAME SAMPLE_R1 SAMPLE_R2 SAMPLE_SINGLE RAW_DIR INPUT_MODE
export QC_OUT_DIR QC_REPORT_DIR HOST_REMOVED_DIR
export ASSEMBLER THREADS SPADES_PARAMS VELVET_K
export ANALYSIS_PROFILE ANALYSIS_PROFILES_CONFIG
export ADVANCED_KMERS
export BLAST_TASK BLAST_WORD_SIZE BLAST_EVALUE
export CONTIGS SKIP_ASSEMBLY SKIP_QC SKIP_HOST_FILTER RESCUE_MODE HOST_INDEX_PREFIX HOST_NAME HOST_ACCESSION HOST_FILTER_ENABLED
export SHORT_FRAGMENT_MODE SHORT_FRAGMENT_MIN_LEN SHORT_FRAGMENT_MAX_LEN SHORT_FRAGMENT_DEDUP
export SHORT_FRAGMENT_BLAST SHORT_FRAGMENT_WORD_SIZE SHORT_FRAGMENT_EVALUE SHORT_FRAGMENT_MIN_PID SHORT_FRAGMENT_MIN_QCOV
export SEARCH_PROFILE_SELECTED SEARCH_PROFILE_IDENTITY SEARCH_PROFILE_REQUESTED
  export EVIDENCE_V2 EVIDENCE_PROFILES EVIDENCE_ROOT EVIDENCE_LIBRARY_MODE EVIDENCE_UMI_MODE EVIDENCE_RESERVATION_TOKEN
export PIPELINE_CONFIG_LOADED=1
EVIDENCE_STATE_FILE="${EVIDENCE_ROOT}/state/${EVIDENCE_RUN_ID}.json"
evidence_state_status() {
  [[ "${EVIDENCE_V2,,}" =~ ^(true|1|yes)$ && -n "$EVIDENCE_RUN_ID" && -f "$EVIDENCE_STATE_FILE" ]] || return 0
  local args=(--state "$EVIDENCE_STATE_FILE" status --value "$1")
  [[ -z "${2:-}" ]] || args+=(--official-v1-status "$2")
  [[ -z "${3:-}" ]] || args+=(--evidence-v2-status "$3")
  python3 "$SCRIPTS_ROOT/evidence/run_state.py" "${args[@]}"
}
evidence_state_stage() {
  [[ "${EVIDENCE_V2,,}" =~ ^(true|1|yes)$ && -n "$EVIDENCE_RUN_ID" && -f "$EVIDENCE_STATE_FILE" ]] || return 0
  local args=(--state "$EVIDENCE_STATE_FILE" stage --id "$1" --status "$2")
  [[ -z "${3:-}" ]] || args+=(--message "$3")
  python3 "$SCRIPTS_ROOT/evidence/run_state.py" "${args[@]}"
}
record_database_preflight_failure() {
  local message="$1"
  export PIPELINE_ETAPA="DATABASE_PREFLIGHT"
  echo "[FATAL]      [DATABASE_PREFLIGHT] [${SAMPLE_NAME}] — ${message}" >&2
  if [[ "${EVIDENCE_V2,,}" =~ ^(true|1|yes)$ && -n "${EVIDENCE_RUN_ID:-}" && -f "${EVIDENCE_STATE_FILE:-}" ]]; then
    python3 "$SCRIPTS_ROOT/evidence/run_state.py" \
      --state "$EVIDENCE_STATE_FILE" status \
      --value failed \
      --official-v1-status failed \
      --evidence-v2-status failed \
      --failure-type INPUT_INVALID \
      --failed-stage database_preflight \
      --failure-message "$message" || \
      echo "[AVISO]      [DATABASE_PREFLIGHT] [${SAMPLE_NAME}] — não foi possível gravar a etapa da falha no estado da execução." >&2
  fi
  exit 65
}
evidence_state_status running running queued
evidence_state_stage input_validation running "Validando FASTQ/FASTA, configuração e parâmetros."
# --- Preflight: validar a entrada efetiva ---
if [[ "$INPUT_MODE" == "CONTIGS" ]]; then
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$CONTIGS"
elif [[ -n "$SAMPLE_SINGLE" ]]; then
  if [[ ! -s "$SAMPLE_SINGLE" ]]; then
    log_fatal "Read single nao encontrado ou vazio: $SAMPLE_SINGLE — Verifique o arquivo."
  fi
  if [[ "$SAMPLE_SINGLE" =~ \.gz$ ]]; then
    gzip -t "$SAMPLE_SINGLE" 2>/dev/null || log_fatal "Read single corrompido ou .gz invalido — Verifique o arquivo antes de prosseguir."
  fi
else
  R1="$SAMPLE_R1"
  R2="$SAMPLE_R2"
  if [[ ! -s "$R1" || ! -s "$R2" ]]; then
    echo "[FATAL]      [QC_PREFLIGHT] [${SAMPLE_NAME}] — FASTQs da amostra nao encontrados ou vazios:" >&2
    echo "             $R1" >&2
    echo "             $R2" >&2
    echo "" >&2
    echo "[DICA] Importe uma amostra com:" >&2
    echo "  bash scripts/ops/stage_sample.sh --id NOME --r1 CAMINHO --r2 CAMINHO [--copy]" >&2
    echo "[DICA] Amostras detectadas em ${RAW_DIR}:" >&2
    ls -1 "${RAW_DIR}"/*_R1.fastq.gz 2>/dev/null | sed -E 's#.*/##; s/_R1\.fastq\.gz$//' | sort -u | sed 's/^/  - /' >&2 || true
    exit 1
  fi

  if [[ "$R1" =~ \.gz$ ]]; then
    gzip -t "$R1" 2>/dev/null || log_fatal "R1 corrompido ou .gz invalido — Verifique o arquivo antes de prosseguir."
  fi
  if [[ "$R2" =~ \.gz$ ]]; then
    gzip -t "$R2" 2>/dev/null || log_fatal "R2 corrompido ou .gz invalido — Verifique o arquivo antes de prosseguir."
  fi

  log_info "Verificando integridade e pareamento dos FASTQs..."
  if [[ "$R1" =~ \.gz$ ]]; then
    r1_lines=$(gzip -cd "$R1" | wc -l)
  else
    r1_lines=$(wc -l < "$R1")
  fi

  if [[ "$R2" =~ \.gz$ ]]; then
    r2_lines=$(gzip -cd "$R2" | wc -l)
  else
    r2_lines=$(wc -l < "$R2")
  fi

  if (( r1_lines % 4 != 0 || r2_lines % 4 != 0 )); then
    log_fatal "FASTQ com numero de linhas nao multiplo de 4 — Verifique a integridade do arquivo."
  fi

  r1_reads=$((r1_lines / 4))
  r2_reads=$((r2_lines / 4))

  if (( r1_reads != r2_reads )); then
    log_fatal "Pareamento inconsistente: R1=${r1_reads} reads, R2=${r2_reads} reads — Confira se os arquivos pertencem ao mesmo par."
  fi
fi
log "Configuração efetiva"
if [[ "$INPUT_MODE" == "READS" ]]; then
  if [[ -n "$SAMPLE_SINGLE" ]]; then
    python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$SAMPLE_SINGLE" >/dev/null
  else
    python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$SAMPLE_R1" --mate "$SAMPLE_R2" >/dev/null
    log_info "FASTQs validados e pareados: ${r1_reads} pares de leituras."
  fi
fi
if [[ " ${SPADES_PARAMS:-} " =~ [[:space:]]-k([[:space:]]|=) ]]; then
  log_fatal "Use --advanced-kmers para configurar k-mers; -k em --spades-params nao e permitido."
fi
if [[ -n "$ADVANCED_KMERS" ]]; then
  [[ "$INPUT_MODE" == "READS" ]] || log_fatal "--advanced-kmers exige reads FASTQ."
  KMER_FASTQ="${SAMPLE_SINGLE:-$SAMPLE_R1}"
  ADVANCED_KMERS="$(python3 "${SCRIPTS_ROOT}/evidence/validate_kmers.py" --kmers "$ADVANCED_KMERS" --fastq "$KMER_FASTQ")"
  if [[ "$ASSEMBLER" == "spades" ]]; then
    SPADES_PARAMS="${SPADES_PARAMS} -k ${ADVANCED_KMERS}"
  fi
fi
evidence_state_stage input_validation "done" "Entrada e parâmetros do pipeline validados."
echo "Amostra: $SAMPLE_NAME"
echo "Perfil de análise: $ANALYSIS_PROFILE"
if [[ "$ASSEMBLER" == "consensus" ]]; then
  echo "Montador: MULTI — SPAdes, metaSPAdes e Velvet"
else
  echo "Montador: $ASSEMBLER"
fi
echo "Processos: $THREADS"
echo "SPADES_PARAMS: ${SPADES_PARAMS:-<vazio>}"
echo "Adaptador R1: ${QC_ADAPTER_R1:-configuração salva ou busca automática}"
echo "Adaptador R2: ${QC_ADAPTER_R2:-configuração salva ou busca automática}"
echo "ADVANCED_KMERS: ${ADVANCED_KMERS:-automatico}"
echo "BLAST_DB: $BLAST_DB"
echo "BLAST: task=$BLAST_TASK word_size=$BLAST_WORD_SIZE evalue=$BLAST_EVALUE"
if [[ "$HOST_FILTER_ENABLED" == "false" || $SKIP_HOST_FILTER -eq 1 ]]; then
  log_warning "Filtro de hospedeiro desligado: leituras e contigs de outros organismos podem permanecer. Contig longo não estabelece origem viral; compare os comprimentos com as referências e revise os alinhamentos."
fi
# Identidade do perfil de busca (GEN-013): A é o padrão público; B e C só
# aparecem aqui quando o run pediu por eles (--search-profiles ou as flags
# equivalentes já existentes).
echo "Perfil de busca: ${SEARCH_PROFILE_SELECTED} (identidade: ${SEARCH_PROFILE_IDENTITY}; pedido: ${SEARCH_PROFILE_REQUESTED:-<padrao>})"
echo "SHORT_FRAGMENT_MODE: $SHORT_FRAGMENT_MODE (range: $SHORT_FRAGMENT_MIN_LEN - $SHORT_FRAGMENT_MAX_LEN, dedup: $SHORT_FRAGMENT_DEDUP)"
echo "SHORT_FRAGMENT_BLAST: $SHORT_FRAGMENT_BLAST (word_size=$SHORT_FRAGMENT_WORD_SIZE evalue=$SHORT_FRAGMENT_EVALUE min_pid=$SHORT_FRAGMENT_MIN_PID min_qcov=$SHORT_FRAGMENT_MIN_QCOV)"
log "[1/6] Verificando ambiente"
export PIPELINE_ETAPA="DATABASE_PREFLIGHT"
if [[ -n "$EVIDENCE_COMPOSITE_DB" ]]; then
  if [[ ! -s "${EVIDENCE_COMPOSITE_DB}.db-manifest.json" ]]; then
    record_database_preflight_failure "Banco composto sem manifesto ${EVIDENCE_COMPOSITE_DB}.db-manifest.json. Prepare o banco antes de executar."
  fi
  if ! python3 "$SCRIPTS_ROOT/evidence/verify_blast_database_manifest.py" "$EVIDENCE_COMPOSITE_DB"; then
    record_database_preflight_failure "Banco composto não corresponde ao manifesto; reconstrua o banco."
  fi
fi
export PIPELINE_ETAPA="QC_PREFLIGHT"
if [[ $AUTO_INSTALL -eq 1 ]]; then
  "$SCRIPTS_ROOT/ops/check_env.sh" --install
else
  "$SCRIPTS_ROOT/ops/check_env.sh"
fi
log "[2/6] Preparando diretórios e bancos"
export PIPELINE_ETAPA="DATABASE_PREFLIGHT"
make -C "$REPO_ROOT" setup_dirs
DATABASE_MANIFEST="${BLAST_DB}.db-manifest.json"
if validate_blast_database "$BLAST_DB" && [[ -s "$DATABASE_MANIFEST" ]]; then
  echo "[INFO] Banco BLAST encontrado em ${BLAST_DB}; conferindo integridade do manifesto."
elif [[ -n "${GENEIN_WORK_ROOT:-}" ]]; then
  record_database_preflight_failure "Execução isolada exige banco BLAST pronto e manifesto: ${DATABASE_MANIFEST}. Prepare o banco antes de executar genein run."
else
  DB_TARGET="db-blast"
  [[ "$DB" == "custom" ]] && DB_TARGET="db"
  if [[ -n "${DB_QUERY:-}" && -n "${DB_QUERY//[[:space:]]/}" ]]; then
    make -C "$REPO_ROOT" "$DB_TARGET" DB="$DB" DB_QUERY="$DB_QUERY"
  else
    make -C "$REPO_ROOT" "$DB_TARGET" DB="$DB"
  fi
fi

if ! validate_blast_database "$BLAST_DB"; then
  record_database_preflight_failure "Banco BLAST ausente, incompleto ou ilegível no prefixo ${BLAST_DB} — a preparação não produziu um banco consultável por blastdbcmd."
fi
if ! python3 "$SCRIPTS_ROOT/evidence/verify_blast_database_manifest.py" "$BLAST_DB" --manifest "$DATABASE_MANIFEST"; then
  record_database_preflight_failure "Banco BLAST não corresponde ao manifesto; reconstrua o banco antes de analisar."
fi

# ── Etapa 2.5: QC com fastp (antes da filtragem de hospedeiro e montagem) ────
export PIPELINE_ETAPA="QC_FASTP"
evidence_state_stage quality_control running "Executando ou avaliando o controle de qualidade do fluxo 1.1."
QC_STATUS="not_applicable"
QC_JSON_REPORT=""
if [[ $SKIP_QC -eq 0 && -z "$CONTIGS" ]]; then
  command -v fastp >/dev/null 2>&1 || log_fatal "fastp não encontrado; instale a dependência ou use --skip-qc explicitamente."
  log "[2.5/6] Controle de qualidade (fastp)"
  "$SCRIPT_DIR/qc_fastp.sh" "$SAMPLE_NAME" "$THREADS"
  QC_JSON_REPORT="${QC_REPORT_DIR}/${SAMPLE_NAME}_fastp.json"
  if [[ -n "$SAMPLE_SINGLE" ]]; then
    CLEANED_SINGLE="${QC_OUT_DIR}/${SAMPLE_NAME}.clean.fastq.gz"
    [[ -s "$CLEANED_SINGLE" && -s "$QC_JSON_REPORT" ]] || log_fatal "fastp não gerou FASTQ single-end e relatório válidos."
    SAMPLE_SINGLE="$CLEANED_SINGLE"
    export SAMPLE_SINGLE
    echo "[INFO] Read single-end atualizada para a versão limpa pelo fastp."
  else
    CLEANED_R1="${QC_OUT_DIR}/${SAMPLE_NAME}_R1.clean.fastq.gz"
    CLEANED_R2="${QC_OUT_DIR}/${SAMPLE_NAME}_R2.clean.fastq.gz"
    [[ -s "$CLEANED_R1" && -s "$CLEANED_R2" && -s "$QC_JSON_REPORT" ]] || log_fatal "fastp não gerou o par FASTQ e relatório válidos."
    SAMPLE_R1="$CLEANED_R1"
    SAMPLE_R2="$CLEANED_R2"
    export SAMPLE_R1 SAMPLE_R2
    echo "[INFO] Reads pareadas atualizadas para versões limpas pelo fastp."
  fi
  QC_STATUS="completed"
else
  log "[2.5/6] Controle de qualidade (fastp) ignorado"
  [[ $SKIP_QC -eq 1 ]] && QC_STATUS="explicitly_skipped"
fi
evidence_state_stage quality_control "done" "Controle de qualidade concluído ou explicitamente ignorado."

# HOST_FILTER_ENABLED já chega normalizado para "true"/"false" pelo
# resolvedor (que aceita os mesmos aliases 1/0, yes/no, sim/nao na entrada).
HOST_FILTER_DISABLED=0
[[ "$HOST_FILTER_ENABLED" == "false" ]] && HOST_FILTER_DISABLED=1
export HOST_FILTER_ENABLED

HOST_FILTER_STATUS="not_applicable"
HOST_FILTER_LOG=""
if [[ $SKIP_HOST_FILTER -eq 0 && $HOST_FILTER_DISABLED -eq 0 && "$INPUT_MODE" == "READS" ]]; then
  export PIPELINE_ETAPA="HOST_FILTER"
  log "[3/6] Filtrando hospedeiro (opcional)"
  [[ -n "$HOST_NAME" ]] || log_fatal "HOST_FILTER_ENABLED=true exige HOST_NAME explícito."
  [[ -n "$HOST_INDEX_PREFIX" ]] || log_fatal "HOST_FILTER_ENABLED=true exige HOST_INDEX_PREFIX explícito."
  resolve_bt2_index "$HOST_INDEX_PREFIX" >/dev/null || \
    log_fatal "Índice completo do hospedeiro '${HOST_NAME}' não encontrado ou inválido em ${HOST_INDEX_PREFIX}."
  "$SCRIPT_DIR/filter_host.sh" "$SAMPLE_NAME"
  HOST_FILTER_LOG="${HOST_REMOVED_DIR}/${SAMPLE_NAME}_host_filter_bowtie2.log"
  # Saturacao total pelo hospedeiro (100% das leituras removidas) e um
  # desfecho estruturado e reconhecido, nao uma falha de ferramenta:
  # filter_host.sh sai com exit code 0 e grava este marcador em vez de
  # promover FASTQs vazios. Quando presente, a amostra encerra aqui, de
  # forma limpa, sem tentar montar FASTQs inexistentes.
  HOST_SATURATION_MARKER="${HOST_REMOVED_DIR}/${SAMPLE_NAME}.host_saturation.json"
  if [[ -s "$HOST_SATURATION_MARKER" ]] && python3 - "$HOST_SATURATION_MARKER" "$SAMPLE_NAME" <<'PY'
import json
import sys
from pathlib import Path

try:
    marker = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
valid = (
    marker.get("schema_version") == "1.0"
    and marker.get("host_saturated") is True
    and marker.get("sample") == sys.argv[2]
    and marker.get("mode") in {"paired", "single"}
)
raise SystemExit(0 if valid else 1)
PY
  then
    log_info "Amostra ${SAMPLE_NAME} encerrada: saturacao total pelo hospedeiro '${HOST_NAME}' — nenhum FASTQ vazio foi promovido. Marcador: ${HOST_SATURATION_MARKER}. Log Bowtie2: ${HOST_FILTER_LOG}."
    HOST_FILTER_STATUS="completed"
    EXECUTION_RECEIPT="${WORK_ROOT}/results/reports/${SAMPLE_NAME}_execution.json"
    python3 "$SCRIPT_DIR/write_execution_receipt.py" \
      --sample "$SAMPLE_NAME" --status completed --exit-code 0 \
      --technical-state COMPLETED --scientific-call negative_confirmed_host_saturated \
      --detail "Todas as leituras alinharam ao hospedeiro '${HOST_NAME}' no indice ${HOST_INDEX_PREFIX}; nenhum FASTQ vazio foi promovido; log Bowtie2 preservado em ${HOST_FILTER_LOG}." \
      --out "$EXECUTION_RECEIPT"
    log "[6/6] Pipeline concluído (saturação total pelo hospedeiro)"
    echo "Amostra: $SAMPLE_NAME"
    echo "Recibo de execução: $EXECUTION_RECEIPT"
    exit 0
  fi
  if [[ -n "$SAMPLE_SINGLE" ]]; then
    FILTERED_SINGLE="${HOST_REMOVED_DIR}/${SAMPLE_NAME}.host_removed.fastq.gz"
    [[ -s "$FILTERED_SINGLE" ]] || log_fatal "Filtro de hospedeiro não gerou FASTQ single-end válido."
    SAMPLE_SINGLE="$FILTERED_SINGLE"
    export SAMPLE_SINGLE
    echo "[INFO] Read single-end atualizada para a versão sem alinhamento ao hospedeiro."
  else
    FILTERED_R1="${HOST_REMOVED_DIR}/${SAMPLE_NAME}_R1.host_removed.fastq.gz"
    FILTERED_R2="${HOST_REMOVED_DIR}/${SAMPLE_NAME}_R2.host_removed.fastq.gz"
    [[ -s "$FILTERED_R1" && -s "$FILTERED_R2" ]] || log_fatal "Filtro de hospedeiro não gerou o par FASTQ válido."
    SAMPLE_R1="$FILTERED_R1"
    SAMPLE_R2="$FILTERED_R2"
    export SAMPLE_R1 SAMPLE_R2
    echo "[INFO] Reads pareadas atualizadas para versões em que ambos os mates não alinharam ao hospedeiro."
  fi
  HOST_FILTER_STATUS="completed"
else
  log "[3/6] Filtro do hospedeiro ignorado"
  if [[ "$INPUT_MODE" != "READS" ]]; then
    echo "[INFO] Entrada por contigs; filtro de hospedeiro não se aplica."
    HOST_FILTER_STATUS="not_applicable"
  elif [[ $HOST_FILTER_DISABLED -eq 1 ]]; then
    echo "[INFO] HOST_FILTER_ENABLED=false; reads seguem sem etapa Bowtie2 de hospedeiro."
    HOST_FILTER_STATUS="disabled_no_host_declared"
  elif [[ $SKIP_HOST_FILTER -eq 1 ]]; then
    HOST_FILTER_STATUS="explicitly_skipped"
  fi
fi
SHORT_READ_COUNT=0
MAXIMUM_READ_LENGTH=0
SHORT_READ_INPUTS=()
if [[ "$INPUT_MODE" == "READS" ]]; then
  if [[ -n "${SAMPLE_SINGLE:-}" ]]; then
    SHORT_READ_INPUTS+=(--fastq "$SAMPLE_SINGLE")
  else
    [[ -z "${SAMPLE_R1:-}" ]] || SHORT_READ_INPUTS+=(--fastq "$SAMPLE_R1")
    [[ -z "${SAMPLE_R2:-}" ]] || SHORT_READ_INPUTS+=(--fastq "$SAMPLE_R2")
  fi
  SHORT_READ_INVENTORY="${WORK_ROOT}/results/short_fragments/${SAMPLE_NAME}_read_lengths.json"
  SHORT_READ_COUNT=$(python3 "$SCRIPT_DIR/short_read_inventory.py" \
    "${SHORT_READ_INPUTS[@]}" --out "$SHORT_READ_INVENTORY") || \
    log_fatal "Falha ao conferir reads disponiveis para recuperacao curta."
  MAXIMUM_READ_LENGTH=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["maximum_read_length_bp"])' "$SHORT_READ_INVENTORY")
fi

export PIPELINE_ETAPA="ASSEMBLY"
evidence_state_stage assembly running "Montagem em execução; SPAdes usa k-mers automáticos por padrão."
log "[4/6] Montagem de contigs"
ASSEMBLY_CONTIGS=""
ASSEMBLY_FAILED=0
if [[ -n "$CONTIGS" ]]; then
  ASSEMBLY_CONTIGS="$(resolve_path "$CONTIGS")"
  log_info "Contigs fornecidos: $ASSEMBLY_CONTIGS (montagem ignorada)"
  METADATA_FILE="${WORK_ROOT}/data/assemblies/${SAMPLE_NAME}_assembly/assembly_metadata.env"
  mkdir -p "$(dirname "$METADATA_FILE")"
  {
    echo "ASSEMBLER_REQUESTED=\"provided\""
    echo "ASSEMBLER_USED=\"provided\""
    echo "ASSEMBLY_FALLBACK=0"
    echo "ASSEMBLY_FAILURE_TYPE=\"NONE\""
    echo "ANALYSIS_PROFILE=\"${ANALYSIS_PROFILE}\""
    echo "ASSEMBLY_STRATEGY=\"provided\""
    echo "RESCUE_TRIGGERED=0"
    echo "INPUT_MODE=\"CONTIGS\""
  } > "$METADATA_FILE"
elif [[ "$ASSEMBLER" != "builder" && "$INPUT_MODE" == "READS" && $SHORT_READ_COUNT -gt 0 && $MAXIMUM_READ_LENGTH -le 20 && $VELVET_K -gt $MAXIMUM_READ_LENGTH && -z "$ADVANCED_KMERS" && -z "${SPADES_PARAMS:-}" ]]; then
  # The default SPAdes k-mer setup starts above this length; Velvet's
  # selected k also exceeds every read. Preserve a direct-read path rather
  # than run an inapplicable assembly. Explicit smaller k remains honoured.
  # builder fica de fora deste atalho: ele registra a propria saida vazia.
  ASSEMBLY_CONTIGS="${WORK_ROOT}/data/assemblies/${SAMPLE_NAME}_assembly/contigs.fa"
  METADATA_FILE="$(dirname "$ASSEMBLY_CONTIGS")/assembly_metadata.env"
  mkdir -p "$(dirname "$ASSEMBLY_CONTIGS")"
  [[ ! -s "$ASSEMBLY_CONTIGS" ]] || cp -p "$ASSEMBLY_CONTIGS" "$(dirname "$ASSEMBLY_CONTIGS")/contigs.previous.fa"
  : > "$ASSEMBLY_CONTIGS"
  ASSEMBLER_USED="none"
  printf 'ASSEMBLER_USED="none"\nASSEMBLY_STATUS="NOT_APPLICABLE_SHORT_READS"\nRESCUE_TRIGGERED=0\nINPUT_MODE="READS"\n' > "$METADATA_FILE"
  log_info "Reads de ate 20 pb: recuperacao direta sem montagem inaplicavel."
else
  set +e
  "$SCRIPT_DIR/assembly_router.sh"
  ASSEMBLY_EXIT_CODE=$?
  set -e
  if [[ $ASSEMBLY_EXIT_CODE -ne 0 ]]; then
    log_warning "Montagem encerrou com falha tecnica (exit ${ASSEMBLY_EXIT_CODE}); logs preservados."
    python3 "$SCRIPT_DIR/write_execution_receipt.py" \
      --sample "$SAMPLE_NAME" --status failed --exit-code "$ASSEMBLY_EXIT_CODE" \
      --technical-state FAILED \
      --detail "O roteador de montagem falhou; ausencia de contigs nao e resultado biologico." \
      --out "${WORK_ROOT}/results/reports/${SAMPLE_NAME}_execution.json"
    exit "$ASSEMBLY_EXIT_CODE"
  fi
  ASSEMBLY_CONTIGS="${WORK_ROOT}/data/assemblies/${SAMPLE_NAME}_assembly/contigs.fa"

  METADATA_FILE="${WORK_ROOT}/data/assemblies/${SAMPLE_NAME}_assembly/assembly_metadata.env"
  if [[ -f "$METADATA_FILE" ]]; then
    # User config/generated metadata is resolved at runtime.
    # shellcheck disable=SC1090
    source "$METADATA_FILE"
  fi

  if [[ ! -s "${ASSEMBLY_CONTIGS}" ]]; then
    log_warning "Montagem falhou ou nao produziu contigs viaveis."
    ASSEMBLY_FAILED=1
    mkdir -p "$(dirname "${ASSEMBLY_CONTIGS}")"
    touch "${ASSEMBLY_CONTIGS}"
  fi
fi
ASSEMBLY_CONSENSUS_MANIFEST="${WORK_ROOT}/data/assemblies/${SAMPLE_NAME}_assembly/assembly_consensus.json"
if [[ "$ANALYSIS_PROFILE" != "assembly-consensus" || "${ASSEMBLER_USED:-}" == "none" || ! -s "$ASSEMBLY_CONSENSUS_MANIFEST" ]]; then
  ASSEMBLY_CONSENSUS_MANIFEST=""
fi
evidence_state_stage assembly "done" "Montagem concluída ou contigs fornecidos validados."

# Artefatos do perfil C (fragmentos curtos). Ficam vazios quando C não roda —
# que é o padrão — e alimentam o manifesto do perfil de busca quando roda.
SF_QUERY_FASTA=""
SF_BLAST_TSV=""
SF_FILTERED_TSV=""
SF_COLLECT_FASTA=""
RESCUE_QUERY_FASTA=""
RESCUE_QUERY_BLAST=""
if [[ "${SHORT_FRAGMENT_MODE:-false}" == "true" && -s "$ASSEMBLY_CONTIGS" ]]; then
  log "[4.5/6] Extração de fragmentos curtos"
  SHORT_INPUT="${WORK_ROOT}/data/assemblies/${SAMPLE_NAME}_assembly/all_kmers_contigs.fa"
  if [[ ! -f "$SHORT_INPUT" ]]; then
    SHORT_INPUT="$ASSEMBLY_CONTIGS"
  fi

  if [[ -f "$SHORT_INPUT" ]]; then
    DEDUP_FLAG=""
    if [[ "${SHORT_FRAGMENT_DEDUP:-false}" == "true" ]]; then
      DEDUP_FLAG="--dedup"
    fi

    python3 "$SCRIPT_DIR/extract_short_fragments.py" \
      --input "$SHORT_INPUT" \
      --sample "$SAMPLE_NAME" \
      --out-dir "${WORK_ROOT}/results/short_fragments" \
      --min-len "$SHORT_FRAGMENT_MIN_LEN" \
      --max-len "$SHORT_FRAGMENT_MAX_LEN" \
      ${DEDUP_FLAG}
    SF_COLLECT_FASTA="${WORK_ROOT}/results/short_fragments/${SAMPLE_NAME}_short_fragments.fa"
  else
    echo "[AVISO] Nenhum FASTA de contigs encontrado para extração de fragmentos curtos."
  fi
fi

  if [[ "${SHORT_FRAGMENT_BLAST:-false}" == "true" ]]; then
    log "[4.6/6] BLAST sensível dos fragmentos curtos"
    SF_UNIQUE="${WORK_ROOT}/results/short_fragments/${SAMPLE_NAME}_short_fragments_unique.fa"
    SF_RAW="${WORK_ROOT}/results/short_fragments/${SAMPLE_NAME}_short_fragments.fa"
    # Preferir deduplicado; cair no bruto se não existi
    if [[ -f "$SF_UNIQUE" ]]; then
      SF_INPUT="$SF_UNIQUE"
    elif [[ -f "$SF_RAW" ]]; then
      SF_INPUT="$SF_RAW"
    else
      SF_INPUT=""
    fi

    if [[ -n "$SF_INPUT" ]]; then
      "$SCRIPT_DIR/blast_short_fragments.sh" \
        --sample "$SAMPLE_NAME" \
        --input  "$SF_INPUT" \
        --db     "$BLAST_DB" \
        --word-size "$SHORT_FRAGMENT_WORD_SIZE" \
        --evalue    "$SHORT_FRAGMENT_EVALUE" \
        --min-pid   "$SHORT_FRAGMENT_MIN_PID" \
        --min-qcov  "$SHORT_FRAGMENT_MIN_QCOV" \
        --threads   "$THREADS"
      SF_QUERY_FASTA="$SF_INPUT"
      SF_BLAST_TSV="${WORK_ROOT}/results/blast/${SAMPLE_NAME}_short_fragments_blast.tsv"
      SF_FILTERED_TSV="${WORK_ROOT}/results/blast/${SAMPLE_NAME}_short_fragments_filtered.tsv"
    else
      echo "[AVISO] Nenhum FASTA de fragmentos curtos encontrado para SHORT_FRAGMENT_BLAST."
      echo "        Ative SHORT_FRAGMENT_MODE=true para gerar os fragmentos antes."
    fi
  fi

export PIPELINE_ETAPA="BLAST"
evidence_state_stage initial_blast running "Executando BLAST inicial do fluxo preservado."
log_info "[5/6] BLAST dos contigs"
OUTDIR="${WORK_ROOT}/results/blast"
mkdir -p "$OUTDIR"

# ── Lógica de Resgate de Reads (Correção 2) ──
max_contig_len=0
if [[ $ASSEMBLY_FAILED -eq 0 && -s "${ASSEMBLY_CONTIGS}" ]]; then
  max_contig_len=$(awk '/^>/ {if (seqlen > max) max = seqlen; seqlen = 0; next} {seqlen += length($0)} END {if (seqlen > max) max = seqlen; print max}' "${ASSEMBLY_CONTIGS}" 2>/dev/null || echo 0)
  max_contig_len=${max_contig_len:-0}
fi

TRIGGER_RESCUE=0
if [[ "$INPUT_MODE" == "CONTIGS" ]]; then
  if [[ ${RESCUE_MODE:-0} -eq 1 ]]; then
    echo "[AVISO] --rescue-mode ignorado para entrada de contigs sem reads." >&2
  fi
elif [[ ${RESCUE_MODE:-0} -eq 1 ]]; then
  TRIGGER_RESCUE=1
  echo "[INFO] Modo de resgate de reads ativado manualmente (--rescue-mode)."
elif [[ $SHORT_READ_COUNT -gt 0 ]]; then
  TRIGGER_RESCUE=1
  echo "[INFO] Ativando resgate: ${SHORT_READ_COUNT} reads de 20–100 pb apos QC/filtro, independentemente dos contigs maiores."
elif [[ $ASSEMBLY_FAILED -eq 1 || $max_contig_len -lt 200 ]]; then
  TRIGGER_RESCUE=1
  echo "[INFO] Ativando resgate automático: maior contig (${max_contig_len} pb) menor que 200 pb."
fi

if [[ $TRIGGER_RESCUE -eq 1 && "$INPUT_MODE" == "READS" ]]; then
  export PIPELINE_ETAPA="RESCUE_READS"
  echo "[INFO] Executando resgate de leituras..."
  RESCUE_FA="${WORK_ROOT}/data/assemblies/${SAMPLE_NAME}_assembly/rescue_reads.fa"
  mkdir -p "$(dirname "${RESCUE_FA}")"
  RESCUE_FA_TMP="${RESCUE_FA}.tmp.$$"
  : > "$RESCUE_FA_TMP"

  cat_fastq_to_fasta() {
    local infile="$1"
    local outfile="$2"
    local mate_suffix="${3:-}"
    if [[ "$infile" =~ \.gz$ ]]; then
      gzip -dc "$infile" | awk -v mate="$mate_suffix" 'NR%4==1{
        header=$0
        sub(/^@/, "", header)
        split(header, parts, /[[:space:]]+/)
        id=parts[1]
        rest=substr(header, length(id) + 1)
        if (mate != "" && id !~ /(\/[12]|[.][12])$/) id=id "/" mate
        print ">" id rest
      } NR%4==2{print}' >> "$outfile"
    else
      awk -v mate="$mate_suffix" 'NR%4==1{
        header=$0
        sub(/^@/, "", header)
        split(header, parts, /[[:space:]]+/)
        id=parts[1]
        rest=substr(header, length(id) + 1)
        if (mate != "" && id !~ /(\/[12]|[.][12])$/) id=id "/" mate
        print ">" id rest
      } NR%4==2{print}' "$infile" >> "$outfile"
    fi
  }

  assert_unique_fasta_headers() {
    local fasta="$1"
    local total unique
    total="$(grep -c '^>' "$fasta" || true)"
    unique="$(awk '/^>/ {print}' "$fasta" | LC_ALL=C sort -u | wc -l | awk '{print $1}')"
    if [[ "$total" != "$unique" ]]; then
      log_fatal "FASTA de resgate possui headers duplicados (${unique}/${total} unicos). Abortando para evitar BLAST com IDs corrompidos."
    fi
  }

  if [[ -n "${SAMPLE_SINGLE:-}" && -s "$SAMPLE_SINGLE" ]]; then
    cat_fastq_to_fasta "$SAMPLE_SINGLE" "$RESCUE_FA_TMP"
  else
    if [[ -n "${SAMPLE_R1:-}" && -s "$SAMPLE_R1" ]]; then
      cat_fastq_to_fasta "$SAMPLE_R1" "$RESCUE_FA_TMP" "1"
    fi
    if [[ -n "${SAMPLE_R2:-}" && -s "$SAMPLE_R2" ]]; then
      cat_fastq_to_fasta "$SAMPLE_R2" "$RESCUE_FA_TMP" "2"
    fi
  fi

  if [[ -s "$RESCUE_FA_TMP" ]]; then
    python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$RESCUE_FA_TMP" >/dev/null || \
      log_fatal "FASTA temporario de resgate invalido."
    mv -f "$RESCUE_FA_TMP" "$RESCUE_FA"
  else
    rm -f "$RESCUE_FA_TMP"
  fi

  if [[ -s "$RESCUE_FA" ]]; then
    assert_unique_fasta_headers "$RESCUE_FA"
    rescue_query_count=$(grep -c '^>' "$RESCUE_FA" || true)
    echo "[INFO] Resgate: ${rescue_query_count} leituras no FASTA de busca; ${SHORT_READ_COUNT:-0} leituras de 20–100 pb motivaram a ativação automática. A busca preserva todas as leituras encaminhadas pelo fluxo atual."
    RESCUE_RAW_OUT="${WORK_ROOT}/results/blast/${SAMPLE_NAME}_read_level_vs_db_raw.tsv"
    RESCUE_FINAL_OUT="${WORK_ROOT}/results/blast/${SAMPLE_NAME}_read_level_candidates.tsv"
    echo "[INFO] Alinhando reads pelo roteador BLAST canônico por comprimento..."
    python3 "${SCRIPTS_ROOT}/evidence/blast_router.py" --query "$RESCUE_FA" --db "$BLAST_DB" \
      --profiles "$EVIDENCE_PROFILES" --recover-short-fragments --threads "$THREADS" --out-combined "$RESCUE_RAW_OUT" \
      --provenance "${RESCUE_RAW_OUT%.tsv}_provenance.json"

    python3 "${SCRIPT_DIR}/filter_rescue_reads.py" --blast-raw "$RESCUE_RAW_OUT" --out-tsv "$RESCUE_FINAL_OUT"
    RESCUE_QUERY_FASTA="$RESCUE_FA"
    RESCUE_QUERY_BLAST="$RESCUE_FINAL_OUT"
    # Atualiza metadados indicando que o resgate foi ativado com sucesso
    if [[ -f "${METADATA_FILE:-}" ]]; then
      METADATA_UPDATED="${METADATA_FILE}.tmp.$$"
      sed 's/RESCUE_TRIGGERED=0/RESCUE_TRIGGERED=1/' "${METADATA_FILE}" > "$METADATA_UPDATED" && \
        mv -f "$METADATA_UPDATED" "${METADATA_FILE}" || rm -f "$METADATA_UPDATED"
    fi
  else
    echo "[AVISO] Nenhuma read de entrada válida encontrada para o resgate."
  fi
fi

export PIPELINE_ETAPA="BLAST"
case "$ASSEMBLER" in
  velvet)     OUT="${OUTDIR}/${SAMPLE_NAME}_k${VELVET_K}_vs_db.tsv" ;;
  metaspades) OUT="${OUTDIR}/${SAMPLE_NAME}_metaspades_vs_db.tsv" ;;
  consensus)  OUT="${OUTDIR}/${SAMPLE_NAME}_assembly_consensus_vs_db.tsv" ;;
  builder)    OUT="${OUTDIR}/${SAMPLE_NAME}_builder_vs_db.tsv" ;;
  *)          OUT="${OUTDIR}/${SAMPLE_NAME}_spades_vs_db.tsv" ;;
esac

if [[ -s "${ASSEMBLY_CONTIGS}" ]]; then
  echo "Parâmetros BLAST de contigs: task=$BLAST_TASK word_size=$BLAST_WORD_SIZE evalue=$BLAST_EVALUE"
  BLAST_TMP="${OUT}.tmp.$$"
  BLAST_REPORT_LIMIT="$(
    python3 - "$SCRIPTS_ROOT" "$BLAST_DB" "$(command -v blastdbcmd)" <<'PY'
import sys

sys.path.insert(0, f"{sys.argv[1]}/evidence")
from blast_router import database_report_limit

print(database_report_limit(sys.argv[2], sys.argv[3]))
PY
  )"
  blastn -task "$BLAST_TASK" -query "$ASSEMBLY_CONTIGS" -db "$(blast_db_arg "$BLAST_DB")" \
    -outfmt '6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps' \
    -max_target_seqs "$BLAST_REPORT_LIMIT" -evalue "$BLAST_EVALUE" -word_size "$BLAST_WORD_SIZE" -num_threads "$THREADS" > "$BLAST_TMP"
  mv -f "$BLAST_TMP" "$OUT"
else
  echo "[INFO] Contigs vazios ou montagem ausente. Gerando arquivo BLAST vazio."
  touch "$OUT"
fi
evidence_state_stage initial_blast "done" "BLAST inicial concluído; resultados V2 continuam experimentais."

# Remove qualquer link anterior para evitar problemas de dangling symlinks
rm -f "${OUTDIR}/${SAMPLE_NAME}_vs_db.tsv"
# Copia o arquivo para criar o link canônico (evita problemas de symlink vazios em NTFS/WSL2)
cp -f "$OUT" "${OUTDIR}/${SAMPLE_NAME}_vs_db.tsv"
echo "Resultado salvo em: $OUT"
# Identidade do perfil de busca congelada como artefato do run (GEN-013).
# É uma declaração do que rodou — nunca liga um perfil — e existe mesmo
# quando Evidence está desligado, para o relatório mínimo poder declará-la.
SEARCH_PROFILE_MANIFEST="${OUTDIR}/${SAMPLE_NAME}_search_profile.json"
python3 "$SCRIPT_DIR/search_profile_manifest.py" \
  --config "$RESOLVED_CONFIG_JSON" --sample "$SAMPLE_NAME" --out "$SEARCH_PROFILE_MANIFEST" \
  --database-manifest "$DATABASE_MANIFEST" \
  --contigs "$ASSEMBLY_CONTIGS" --contig-blast-tsv "$OUT" \
  --short-fragment-fasta "$SF_QUERY_FASTA" \
  --short-fragment-blast-tsv "$SF_BLAST_TSV" \
  --short-fragment-filtered-tsv "$SF_FILTERED_TSV"
echo "Perfil de busca registrado em: $SEARCH_PROFILE_MANIFEST"
REPORT="${WORK_ROOT}/results/reports/${SAMPLE_NAME}_summary.md"
"$SCRIPT_DIR/report_minimal.sh" --sample "$SAMPLE_NAME" --contigs "$ASSEMBLY_CONTIGS" --blast "$OUT" --out "$REPORT" \
  --search-profile "$SEARCH_PROFILE_MANIFEST"
evidence_state_status running "done" running
case "${EVIDENCE_V2,,}" in
  true|1|yes)
    CANDIDATE_QUERIES="${WORK_ROOT}/results/short_fragments/${SAMPLE_NAME}_candidate_queries.fa"
    CANDIDATE_MANIFEST="${WORK_ROOT}/results/short_fragments/${SAMPLE_NAME}_candidate_queries.json"
    CANDIDATE_SUPPLEMENT="${WORK_ROOT}/results/short_fragments/${SAMPLE_NAME}_candidate_supplement.fa"
    COLLECT_ARGS=(--contigs "$ASSEMBLY_CONTIGS" --out "$CANDIDATE_QUERIES" --manifest "$CANDIDATE_MANIFEST" --supplement-out "$CANDIDATE_SUPPLEMENT")
    [[ -z "$SF_COLLECT_FASTA" ]] || COLLECT_ARGS+=(--short-fasta "$SF_COLLECT_FASTA")
    if [[ "$INPUT_MODE" == "READS" ]]; then
      COLLECT_ARGS+=("${SHORT_READ_INPUTS[@]}")
    fi
    [[ -z "$RESCUE_QUERY_FASTA" ]] || COLLECT_ARGS+=(--rescue-fasta "$RESCUE_QUERY_FASTA" --rescue-candidates "$RESCUE_QUERY_BLAST")
    python3 "$SCRIPT_DIR/collect_candidate_queries.py" "${COLLECT_ARGS[@]}"
    EVIDENCE_ARGS=(
      --sample "$SAMPLE_NAME" --queries "$CANDIDATE_QUERIES" --query-manifest "$CANDIDATE_MANIFEST"
      --profiles "$EVIDENCE_PROFILES" --evidence-root "$EVIDENCE_ROOT"
      --library-mode "$EVIDENCE_LIBRARY_MODE" --umi-mode "$EVIDENCE_UMI_MODE" --threads "$THREADS"
      --qc-status "$QC_STATUS" --host-filter-status "$HOST_FILTER_STATUS"
      --qc-min-length "$QC_MIN_LEN" --qc-min-quality "$QC_MIN_QUAL"
    )
    EVIDENCE_ARGS+=(--role "$EVIDENCE_ROLE")
    if [[ "$QC_STATUS" == "completed" && -z "${SAMPLE_SINGLE:-}" ]]; then
      EVIDENCE_ARGS+=(--qc-minimum-overlap-bp 30)
    fi
    if [[ "$QC_STATUS" == "completed" ]]; then
      EVIDENCE_ARGS+=(--qc-adapter-r1 "${QC_ADAPTER_R1:-automatic_detection}" --qc-adapter-r2 "${QC_ADAPTER_R2:-automatic_detection}")
    fi
    [[ -z "$ASSEMBLY_CONSENSUS_MANIFEST" ]] || \
      EVIDENCE_ARGS+=(--assembly-manifest "$ASSEMBLY_CONSENSUS_MANIFEST")
    [[ -z "${ASSEMBLER_USED:-}" ]] || EVIDENCE_ARGS+=(--assembly-method "$ASSEMBLER_USED")
    [[ -z "$QC_JSON_REPORT" ]] || EVIDENCE_ARGS+=(--qc-report "$QC_JSON_REPORT")
    [[ -z "$HOST_FILTER_LOG" ]] || EVIDENCE_ARGS+=(--host-filter-log "$HOST_FILTER_LOG")
    [[ -z "$EVIDENCE_EXPECTED_TARGET" ]] || EVIDENCE_ARGS+=(--expected-target "$EVIDENCE_EXPECTED_TARGET")
    [[ -z "$EVIDENCE_RUN_ID" ]] || EVIDENCE_ARGS+=(--run-id "$EVIDENCE_RUN_ID")
    [[ -z "$EVIDENCE_BATCH_ID" ]] || EVIDENCE_ARGS+=(--batch-id "$EVIDENCE_BATCH_ID")
    if [[ -n "$EVIDENCE_COMPOSITE_DB" ]]; then
      EVIDENCE_ARGS+=(--composite-db "$EVIDENCE_COMPOSITE_DB")
      [[ -z "$EVIDENCE_SUBJECT_LABELS" ]] || EVIDENCE_ARGS+=(--subject-labels "$EVIDENCE_SUBJECT_LABELS")
    else
      CANDIDATE_SHORT_BLAST="${OUTDIR}/${SAMPLE_NAME}_candidate_short.tsv"
      CANDIDATE_LONG_BLAST="${OUTDIR}/${SAMPLE_NAME}_candidate_conventional.tsv"
      if [[ -s "$CANDIDATE_SUPPLEMENT" ]]; then
        python3 "${SCRIPTS_ROOT}/evidence/blast_router.py" --query "$CANDIDATE_SUPPLEMENT" --db "$BLAST_DB" \
          --profiles "$EVIDENCE_PROFILES" --recover-short-fragments --threads "$THREADS" \
          --out-short "$CANDIDATE_SHORT_BLAST" --out-conventional "$CANDIDATE_LONG_BLAST" \
          --provenance "${OUTDIR}/${SAMPLE_NAME}_candidate_routing.json"
        EVIDENCE_ARGS+=(--supplement-routing "${OUTDIR}/${SAMPLE_NAME}_candidate_routing.json")
      else
        : > "$CANDIDATE_SHORT_BLAST"; : > "$CANDIDATE_LONG_BLAST"
      fi
      EVIDENCE_ARGS+=(--blast "${BLAST_TASK}=${OUT}" --blast "blastn-short=${CANDIDATE_SHORT_BLAST}" --blast "blastn=${CANDIDATE_LONG_BLAST}")
      EVIDENCE_ARGS+=(--database-manifest "$DATABASE_MANIFEST")
      # Queries are searched together: do not append legacy short TSVs with
      # different identifiers or count duplicate searches as new evidence.
    fi
    # Remapping can accompany either external BLAST or the composite search.
    [[ -z "$EVIDENCE_PANEL_FASTA" ]] || EVIDENCE_ARGS+=(--panel-fasta "$EVIDENCE_PANEL_FASTA")
    [[ -z "$EVIDENCE_PANEL_INDEX" ]] || EVIDENCE_ARGS+=(--panel-index "$EVIDENCE_PANEL_INDEX")
    EVIDENCE_ARGS+=(--search-profile-manifest "$SEARCH_PROFILE_MANIFEST")
    if [[ "$INPUT_MODE" == "READS" ]]; then
      if [[ -n "${SAMPLE_SINGLE:-}" ]]; then
        EVIDENCE_ARGS+=(--single "$SAMPLE_SINGLE")
      elif [[ -n "${SAMPLE_R1:-}" && -n "${SAMPLE_R2:-}" ]]; then
        EVIDENCE_ARGS+=(--r1 "$SAMPLE_R1" --r2 "$SAMPLE_R2")
      fi
    fi
    if "$SCRIPTS_ROOT/evidence/run.sh" "${EVIDENCE_ARGS[@]}"; then
      :
    else
      evidence_exit_code=$?
      log_warning "A análise Evidence 2.0 falhou; os resultados parciais foram preservados."
      exit "$evidence_exit_code"
    fi
    ;;
esac
# The completed empty assembly is a structural outcome, not a biological negative.
# Emit only after downstream stages succeed; rescue outputs remain available.
if [[ "$INPUT_MODE" == "READS" && -f "$ASSEMBLY_CONTIGS" && ! -s "$ASSEMBLY_CONTIGS" ]]; then
  python3 "$SCRIPT_DIR/write_execution_receipt.py" \
    --sample "$SAMPLE_NAME" --status completed --exit-code 0 \
    --technical-state COMPLETED --scientific-call no_assembly \
    --detail "Montagem concluida sem contigs; material nao avaliavel, sem inferencia de ausencia biologica." \
    --out "${WORK_ROOT}/results/reports/${SAMPLE_NAME}_execution.json"
fi

echo "Resumo salvo em: $REPORT"
log "[6/6] Pipeline concluído"
echo "Amostra: $SAMPLE_NAME"
echo "Perfil: $ANALYSIS_PROFILE"
echo "Montador: $ASSEMBLER_LABEL"
echo "Contigs: $ASSEMBLY_CONTIGS"
echo "BLAST: $OUT"
echo "Relatório: $REPORT"
