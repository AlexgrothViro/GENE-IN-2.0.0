#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"
# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"

# The main pipeline has already resolved CLI/config precedence.
if [[ "${PIPELINE_CONFIG_LOADED:-0}" != "1" ]]; then
  if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
  fi
fi

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/common.sh"
# Assembler failures are classified below and may trigger a fallback.
set +e

RAW_DIR="$(resolve_path "${RAW_DIR:-data/raw}")"
ASSEMBLY_DIR="$(resolve_path "${ASSEMBLY_DIR:-data/assemblies}")"
SAMPLE_NAME="${SAMPLE_NAME:-${SAMPLE:-}}"
if [[ -z "$SAMPLE_NAME" ]]; then
  log_error "Informe SAMPLE_NAME ou SAMPLE explicitamente."
fi
SAMPLE_NAME="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE_NAME")" || exit 2
SAMPLE_ID="${SAMPLE_ID:-$SAMPLE_NAME}"
SAMPLE_KEY="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE_ID")" || exit 2
SAFE_SAMPLE_KEY="$SAMPLE_KEY"

ASSEMBLER="${ASSEMBLER:-velvet}"
ASSEMBLER="${ASSEMBLER,,}"
ANALYSIS_PROFILE="${ANALYSIS_PROFILE:-default}"
ANALYSIS_PROFILES_CONFIG="${ANALYSIS_PROFILES_CONFIG:-${REPO_ROOT}/config/analysis_profiles.json}"
THREADS="${THREADS:-4}"
SPADES_PARAMS="${SPADES_PARAMS:-}"
VELVET_K="${VELVET_K:-31}"

python3 "${SCRIPT_DIR}/analysis_profiles.py" \
  --config "$ANALYSIS_PROFILES_CONFIG" --profile "$ANALYSIS_PROFILE" >/dev/null || exit 2
PROFILE_STRATEGY="$(
  python3 "${SCRIPT_DIR}/analysis_profiles.py" \
    --config "$ANALYSIS_PROFILES_CONFIG" --profile "$ANALYSIS_PROFILE" --field strategy
)" || exit 2
PROFILE_MINIMUM_SUCCESSFUL="$(
  python3 "${SCRIPT_DIR}/analysis_profiles.py" \
    --config "$ANALYSIS_PROFILES_CONFIG" --profile "$ANALYSIS_PROFILE" \
    --field minimum_successful_assemblers
)" || exit 2
if [[ "$PROFILE_STRATEGY" == "consensus" ]]; then
  ASSEMBLER="consensus"
fi
case "$ASSEMBLER" in
  velvet|spades|metaspades|consensus|builder) ;;
  *) log_error "Montador invalido: '$ASSEMBLER'. Use velvet, spades, metaspades, builder ou o perfil assembly-consensus." ;;
esac
if ! [[ "$THREADS" =~ ^[1-9][0-9]*$ ]]; then
  log_error "THREADS deve ser um inteiro positivo: '$THREADS'."
fi
if ! [[ "$VELVET_K" =~ ^[0-9]+$ ]] || (( VELVET_K < 15 || VELVET_K > 127 || VELVET_K % 2 == 0 )); then
  log_error "VELVET_K deve ser impar e estar entre 15 e 127: '$VELVET_K'."
fi

RAW_SINGLE=""
RAW1=""
RAW2=""
if [[ -n "${SAMPLE_SINGLE:-}" && ( -n "${SAMPLE_R1:-}" || -n "${SAMPLE_R2:-}" ) ]]; then
  log_error "Use SAMPLE_SINGLE ou SAMPLE_R1/SAMPLE_R2, nunca os dois modos."
elif [[ -n "${SAMPLE_SINGLE:-}" ]]; then
  RAW_SINGLE="$(resolve_path "$SAMPLE_SINGLE")"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$RAW_SINGLE" >/dev/null || exit 2
else
  if [[ -n "${SAMPLE_R1:-}" || -n "${SAMPLE_R2:-}" ]]; then
    [[ -n "${SAMPLE_R1:-}" && -n "${SAMPLE_R2:-}" ]] || \
      log_error "SAMPLE_R1 e SAMPLE_R2 devem ser informados juntos."
    RAW1="$(resolve_path "$SAMPLE_R1")"
    RAW2="$(resolve_path "$SAMPLE_R2")"
  else
    RAW1="${RAW_DIR}/${SAMPLE_KEY}_R1.fastq.gz"
    RAW2="${RAW_DIR}/${SAMPLE_KEY}_R2.fastq.gz"
  fi
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$RAW1" --mate "$RAW2" >/dev/null || exit 2
fi

log_info "[PIPELINE] Amostra: $SAMPLE_NAME"
log_info "[PIPELINE] Identificador da amostra: $SAMPLE_KEY"
log_info "[PIPELINE] Perfil de análise: $ANALYSIS_PROFILE"
log_info "[PIPELINE] Montador: $ASSEMBLER"
if [[ -n "$RAW_SINGLE" ]]; then
  log_info "[PIPELINE] Input single-end: $RAW_SINGLE"
else
  log_info "[PIPELINE] Entradas pareadas: $RAW1 / $RAW2"
fi

STD_ASM_DIR="${ASSEMBLY_DIR}/${SAMPLE_KEY}_assembly"
mkdir -p "$STD_ASM_DIR"
export PIPELINE_ETAPA="ASSEMBLY"

LAST_CONTIGS_SRC=""
LAST_MAX_CONTIG_LEN=0

run_single_assembler() {
  local asm="$1"
  local rc=0
  local contigs_src=""
  local asm_log_dir="${GENEIN_WORK_ROOT:-$REPO_ROOT}/logs/assembly"
  local stdout_log="${asm_log_dir}/${SAFE_SAMPLE_KEY}_${asm}.stdout.log"
  local stderr_log="${asm_log_dir}/${SAFE_SAMPLE_KEY}_${asm}.stderr.log"
  mkdir -p "$asm_log_dir"
  : > "$stdout_log"
  : > "$stderr_log"
  LAST_CONTIGS_SRC=""
  LAST_MAX_CONTIG_LEN=0

  log_info "Tentando montar com: $asm"
  case "$asm" in
    metaspades)
      contigs_src="${ASSEMBLY_DIR}/${SAFE_SAMPLE_KEY}_metaspades/contigs.fasta"
      if [[ -n "$RAW_SINGLE" ]]; then
        log_warning "metaSPAdes requer biblioteca curta paired-end; tentativa single-end recusada."
        return 1
      fi
      R1="$RAW1" R2="$RAW2" ASSEMBLY_DIR="$ASSEMBLY_DIR" \
        "${SCRIPT_DIR}/assemblers/metaspades.sh" "$SAFE_SAMPLE_KEY" "$THREADS" "$SPADES_PARAMS" \
        > "$stdout_log" 2> "$stderr_log"
      rc=$?
      ;;
    spades)
      contigs_src="${ASSEMBLY_DIR}/${SAFE_SAMPLE_KEY}_spades/contigs.fasta"
      if [[ -n "$RAW_SINGLE" ]]; then
        SAMPLE_SINGLE="$RAW_SINGLE" ASSEMBLY_DIR="$ASSEMBLY_DIR" \
          "${SCRIPT_DIR}/assemblers/spades.sh" "$SAFE_SAMPLE_KEY" "$THREADS" "$SPADES_PARAMS" "spades" \
          > "$stdout_log" 2> "$stderr_log"
      else
        R1="$RAW1" R2="$RAW2" ASSEMBLY_DIR="$ASSEMBLY_DIR" \
          "${SCRIPT_DIR}/assemblers/spades.sh" "$SAFE_SAMPLE_KEY" "$THREADS" "$SPADES_PARAMS" "spades" \
          > "$stdout_log" 2> "$stderr_log"
      fi
      rc=$?
      ;;
    velvet)
      contigs_src="${ASSEMBLY_DIR}/${SAFE_SAMPLE_KEY}_velvet_k${VELVET_K}/contigs.fa"
      if [[ -n "$RAW_SINGLE" ]]; then
        SAMPLE_SINGLE="$RAW_SINGLE" ASSEMBLY_DIR="$ASSEMBLY_DIR" \
          "${SCRIPT_DIR}/assemblers/velvet.sh" "$SAFE_SAMPLE_KEY" "$VELVET_K" "${VELVET_OPTS:-}" \
          > "$stdout_log" 2> "$stderr_log"
      else
        R1="$RAW1" R2="$RAW2" ASSEMBLY_DIR="$ASSEMBLY_DIR" \
          "${SCRIPT_DIR}/assemblers/velvet.sh" "$SAFE_SAMPLE_KEY" "$VELVET_K" "${VELVET_OPTS:-}" \
          > "$stdout_log" 2> "$stderr_log"
      fi
      rc=$?
      ;;
    builder)
      contigs_src="${ASSEMBLY_DIR}/${SAFE_SAMPLE_KEY}_builder/contigs.fasta"
      if [[ -n "$RAW_SINGLE" ]]; then
        SAMPLE_SINGLE="$RAW_SINGLE" ASSEMBLY_DIR="$ASSEMBLY_DIR" BUILDER_MOTOR="${BUILDER_MOTOR:-v1}" \
          "${SCRIPT_DIR}/assemblers/builder.sh" "$SAFE_SAMPLE_KEY" "$THREADS" \
          > "$stdout_log" 2> "$stderr_log"
      else
        R1="$RAW1" R2="$RAW2" ASSEMBLY_DIR="$ASSEMBLY_DIR" BUILDER_MOTOR="${BUILDER_MOTOR:-v1}" \
          "${SCRIPT_DIR}/assemblers/builder.sh" "$SAFE_SAMPLE_KEY" "$THREADS" \
          > "$stdout_log" 2> "$stderr_log"
      fi
      rc=$?
      ;;
  esac

  if [[ $rc -ne 0 ]]; then
    log_warning "Montador $asm falhou com exit code $rc (falha dura). Logs: stdout=${stdout_log}; stderr=${stderr_log}"
    return 1
  fi
  if [[ ! -s "$contigs_src" ]]; then
    log_warning "Montador $asm nao gerou contigs (falha branda)."
    return 3
  fi
  if ! python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$contigs_src" >/dev/null; then
    log_warning "Montador $asm gerou FASTA invalido (falha dura): $contigs_src"
    return 1
  fi

  LAST_CONTIGS_SRC="$contigs_src"
  LAST_MAX_CONTIG_LEN="$(
    awk '/^>/ {if (seqlen > max) max = seqlen; seqlen = 0; next}
         {seqlen += length($0)}
         END {if (seqlen > max) max = seqlen; print (max + 0)}' "$contigs_src"
  )"
  # builder publica de proposito sequencias de 20 pb ou mais. O limiar de
  # 200 pb continua valendo para velvet, spades e metaspades.
  if [[ "$asm" != "builder" ]] && (( LAST_MAX_CONTIG_LEN < 200 )); then
    log_warning "Maior contig gerado por $asm (${LAST_MAX_CONTIG_LEN} bp) menor que 200 bp (falha branda)."
    return 2
  fi
  log_info "Montador $asm concluído. Maior contig: ${LAST_MAX_CONTIG_LEN} pb."
  return 0
}

ASSEMBLER_REQUESTED="$ASSEMBLER"
ASSEMBLER_USED="$ASSEMBLER"
ASSEMBLY_FALLBACK=0
ASSEMBLY_FAILURE_TYPE="NONE"
CONSENSUS_MANIFEST_SRC=""
CONSENSUS_WORK=""

if [[ "$ASSEMBLER" == "consensus" ]]; then
  CONSENSUS_WORK="$(mktemp -d "${STD_ASM_DIR}/.assembly-consensus.XXXXXX")" || exit 1
  mapfile -t CONSENSUS_ASSEMBLERS < <(
    python3 "${SCRIPT_DIR}/analysis_profiles.py" \
      --config "$ANALYSIS_PROFILES_CONFIG" --profile "$ANALYSIS_PROFILE" --field assemblers
  )
  CONSENSUS_INPUT_ARGS=()
  CONSENSUS_STATUS_ARGS=()
  SUCCESSFUL_ASSEMBLERS=()
  EMPTY_ASSEMBLERS=()
  CONSENSUS_MAX_CONTIG_LEN=0
  for candidate_assembler in "${CONSENSUS_ASSEMBLERS[@]}"; do
    if [[ "$candidate_assembler" == "metaspades" && -n "$RAW_SINGLE" ]]; then
      CONSENSUS_STATUS_ARGS+=(--status "metaspades=NOT_APPLICABLE")
      log_warning "metaSPAdes não é aplicável a esta entrada single-end."
      continue
    fi
    run_single_assembler "$candidate_assembler"
    candidate_status=$?
    case "$candidate_status" in
      0)
        CONSENSUS_STATUS_ARGS+=(--status "${candidate_assembler}=SUCCESS")
        ;;
      2)
        CONSENSUS_STATUS_ARGS+=(--status "${candidate_assembler}=SOFT")
        ;;
      3)
        CONSENSUS_STATUS_ARGS+=(--status "${candidate_assembler}=EMPTY")
        EMPTY_ASSEMBLERS+=("$candidate_assembler")
        continue
        ;;
      *)
        CONSENSUS_STATUS_ARGS+=(--status "${candidate_assembler}=HARD")
        continue
        ;;
    esac
    SUCCESSFUL_ASSEMBLERS+=("$candidate_assembler")
    CONSENSUS_INPUT_ARGS+=(--input "${candidate_assembler}=${LAST_CONTIGS_SRC}")
    if (( LAST_MAX_CONTIG_LEN > CONSENSUS_MAX_CONTIG_LEN )); then
      CONSENSUS_MAX_CONTIG_LEN="$LAST_MAX_CONTIG_LEN"
    fi
  done

  ASSEMBLER_USED="$(IFS=,; echo "${SUCCESSFUL_ASSEMBLERS[*]}")"
  if ((${#SUCCESSFUL_ASSEMBLERS[@]} == 0 && ${#EMPTY_ASSEMBLERS[@]} == 0)); then
    ASM_STATUS=1
    ASSEMBLY_FAILURE_TYPE="HARD"
    LAST_CONTIGS_SRC=""
    LAST_MAX_CONTIG_LEN=0
  else
    ASM_STATUS=0
python3 "${SCRIPTS_ROOT}/evidence/assembly_consensus.py" combine \
      "${CONSENSUS_INPUT_ARGS[@]}" "${CONSENSUS_STATUS_ARGS[@]}" \
      --out-fasta "${CONSENSUS_WORK}/contigs.fa" \
      --out-manifest "${CONSENSUS_WORK}/assembly_consensus.json" \
      --minimum-successful "$PROFILE_MINIMUM_SUCCESSFUL" \
      --profile "$ANALYSIS_PROFILE" || {
        ASM_STATUS=1
        ASSEMBLY_FAILURE_TYPE="HARD"
        LAST_CONTIGS_SRC=""
        LAST_MAX_CONTIG_LEN=0
        log_error "Falha ao consolidar consenso entre montadores."
      }
    if [[ "$ASM_STATUS" -eq 1 ]]; then
      :
    else
    LAST_CONTIGS_SRC="${CONSENSUS_WORK}/contigs.fa"
    CONSENSUS_MANIFEST_SRC="${CONSENSUS_WORK}/assembly_consensus.json"
    LAST_MAX_CONTIG_LEN="$CONSENSUS_MAX_CONTIG_LEN"
    ASM_STATUS=0
    if ((${#SUCCESSFUL_ASSEMBLERS[@]} < PROFILE_MINIMUM_SUCCESSFUL)); then
      ASSEMBLY_FAILURE_TYPE="SOFT"
      log_warning "Consenso incompleto: ${#SUCCESSFUL_ASSEMBLERS[@]}/${#CONSENSUS_ASSEMBLERS[@]} montadores do perfil produziram contigs; mínimo exigido pelo perfil: ${PROFILE_MINIMUM_SUCCESSFUL}. Consulte os logs individuais de montagem."
    else
      ASSEMBLY_FAILURE_TYPE="NONE"
    fi
    fi
  fi
else
  run_single_assembler "$ASSEMBLER"
  ASM_STATUS=$?

  if [[ $ASM_STATUS -eq 1 && "$ASSEMBLER" == "builder" ]]; then
    log_warning "Montador builder falhou. Nenhum fallback para velvet, spades ou metaspades sera aplicado."
  elif [[ $ASM_STATUS -eq 1 ]]; then
    ASSEMBLY_FALLBACK=1
    log_recovered "Montador inicial $ASSEMBLER reportou falha dura. Iniciando fallback."
    case "$ASSEMBLER" in
      spades) FALLBACK_ORDER=(metaspades velvet) ;;
      metaspades) FALLBACK_ORDER=(spades velvet) ;;
      velvet) FALLBACK_ORDER=(spades metaspades) ;;
    esac
    ASM_STATUS=1
    for fallback in "${FALLBACK_ORDER[@]}"; do
      ASSEMBLER_USED="$fallback"
      run_single_assembler "$fallback"
      ASM_STATUS=$?
      [[ $ASM_STATUS -eq 1 ]] || break
    done
  fi

  case "$ASM_STATUS" in
    0)
      ASSEMBLY_FAILURE_TYPE="NONE"
      ;;
    2|3)
      ASSEMBLY_FAILURE_TYPE="SOFT"
      # Short contigs remain valid computational artifacts. Keeping them does not
      # promote their scientific evidence level; it only prevents data loss.
      ;;
    *)
      ASSEMBLY_FAILURE_TYPE="HARD"
      LAST_CONTIGS_SRC=""
      LAST_MAX_CONTIG_LEN=0
      if [[ "$ASSEMBLER" == "builder" ]]; then
        log_warning "Montador builder falhou. O resultado fica registrado como HARD e nenhum outro montador foi acionado."
      else
        log_warning "Todos os montadores aplicaveis falharam."
      fi
      ;;
  esac
fi

# Publish current-run canonical artifacts without ever treating an old contig
# file as output from this attempt. The previous non-empty canonical FASTA is
# retained as a recoverable sidecar before replacement.
CONTIGS_TMP="$(mktemp "${STD_ASM_DIR}/.contigs.fa.XXXXXX")" || exit 1
METADATA_TMP="$(mktemp "${STD_ASM_DIR}/.assembly_metadata.env.XXXXXX")" || {
  rm -f "$CONTIGS_TMP"
  exit 1
}
CONSENSUS_MANIFEST_TMP=""
if [[ -n "$CONSENSUS_MANIFEST_SRC" ]]; then
  CONSENSUS_MANIFEST_TMP="$(mktemp "${STD_ASM_DIR}/.assembly_consensus.json.XXXXXX")" || exit 1
  cp -f "$CONSENSUS_MANIFEST_SRC" "$CONSENSUS_MANIFEST_TMP" || exit 1
fi
trap 'rm -f "$CONTIGS_TMP" "$METADATA_TMP" "$CONSENSUS_MANIFEST_TMP"; [[ -z "$CONSENSUS_WORK" ]] || rm -rf "$CONSENSUS_WORK"' EXIT

if [[ -n "$LAST_CONTIGS_SRC" ]]; then
  cp -f "$LAST_CONTIGS_SRC" "$CONTIGS_TMP" || exit 1
else
  : > "$CONTIGS_TMP"
fi

{
  printf 'ASSEMBLER_REQUESTED="%s"\n' "$ASSEMBLER_REQUESTED"
  printf 'ASSEMBLER_USED="%s"\n' "$ASSEMBLER_USED"
  printf 'ASSEMBLY_FALLBACK=%s\n' "$ASSEMBLY_FALLBACK"
  printf 'ASSEMBLY_FAILURE_TYPE="%s"\n' "$ASSEMBLY_FAILURE_TYPE"
  printf 'ASSEMBLY_MAX_CONTIG_LEN=%s\n' "$LAST_MAX_CONTIG_LEN"
  printf 'ANALYSIS_PROFILE="%s"\n' "$ANALYSIS_PROFILE"
  printf 'ASSEMBLY_STRATEGY="%s"\n' "$PROFILE_STRATEGY"
  printf 'ASSEMBLY_CONSENSUS_MINIMUM=%s\n' "$PROFILE_MINIMUM_SUCCESSFUL"
  printf 'RESCUE_TRIGGERED=0\n'
  printf 'INPUT_MODE="READS"\n'
  if [[ "$ASSEMBLER_REQUESTED" == "builder" ]]; then
    BUILDER_PROVENANCE="${ASSEMBLY_DIR}/${SAFE_SAMPLE_KEY}_builder/builder_provenance.env"
    if [[ -f "$BUILDER_PROVENANCE" ]]; then
      while IFS= read -r BUILDER_LINE || [[ -n "$BUILDER_LINE" ]]; do
        if [[ "$BUILDER_LINE" =~ ^[A-Z0-9_]+=\"[A-Za-z0-9._+-]*\"$ ]]; then
          printf '%s\n' "$BUILDER_LINE"
        fi
      done < "$BUILDER_PROVENANCE"
    else
      printf 'BUILDER_VERSION="unavailable"\n'
      printf 'BUILDER_COMMIT="unavailable"\n'
      printf 'BUILDER_STATUS="UNRECORDED"\n'
    fi
  fi
} > "$METADATA_TMP"

if [[ -s "${STD_ASM_DIR}/contigs.fa" ]]; then
  PREVIOUS_TMP="$(mktemp "${STD_ASM_DIR}/.contigs.previous.fa.XXXXXX")" || exit 1
  cp -p "${STD_ASM_DIR}/contigs.fa" "$PREVIOUS_TMP" || exit 1
  mv -f "$PREVIOUS_TMP" "${STD_ASM_DIR}/contigs.previous.fa" || exit 1
fi
mv -f "$CONTIGS_TMP" "${STD_ASM_DIR}/contigs.fa" || exit 1
mv -f "$METADATA_TMP" "${STD_ASM_DIR}/assembly_metadata.env" || exit 1
if [[ -n "$CONSENSUS_MANIFEST_TMP" ]]; then
  mv -f "$CONSENSUS_MANIFEST_TMP" "${STD_ASM_DIR}/assembly_consensus.json" || exit 1
fi
if [[ -n "$CONSENSUS_WORK" ]]; then
  rm -rf "$CONSENSUS_WORK"
  CONSENSUS_WORK=""
fi
trap - EXIT

log_info "Artefatos canonicos da montagem atualizados em ${STD_ASM_DIR}."
if [[ "$ASSEMBLY_FAILURE_TYPE" == "HARD" ]]; then
  exit 1
fi
exit 0
