#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
LEGACY_CONFIG="${REPO_ROOT}/config.env"

# Se chamado pelo pipeline principal, não recarregar config.env.
INCOMING_SPADES_PARAMS="${SPADES_PARAMS:-}"
INCOMING_ASSEMBLER="${ASSEMBLER:-}"

if [[ "${PIPELINE_CONFIG_LOADED:-0}" != "1" ]]; then
  if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${CONFIG_FILE}"
  fi
fi

if [[ -n "$INCOMING_SPADES_PARAMS" ]]; then
  SPADES_PARAMS="$INCOMING_SPADES_PARAMS"
fi
if [[ -n "$INCOMING_ASSEMBLER" ]]; then
  ASSEMBLER="$INCOMING_ASSEMBLER"
fi

# Se a variável não estiver no ambiente, podemos tentar carregá-la do config
if [[ -z "${FRAGMENT_HUNTER_KEEP_ALL_KMERS:-}" ]]; then
  if [[ -f "${CONFIG_FILE}" ]]; then
    FRAGMENT_HUNTER_KEEP_ALL_KMERS=$(grep -E "^[[:space:]]*(export[[:space:]]+)?FRAGMENT_HUNTER_KEEP_ALL_KMERS=" "${CONFIG_FILE}" | cut -d= -f2- | tr -d '"' | tr -d "'") || true
  fi
fi
FRAGMENT_HUNTER_KEEP_ALL_KMERS="${FRAGMENT_HUNTER_KEEP_ALL_KMERS:-false}"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/common.sh"

SAMPLE="${1:?SAMPLE obrigatório}"
THREADS="${2:-4}"
SAMPLE="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE")"
SPADES_PARAMS="${3:-${SPADES_PARAMS:-}}"
SPADES_MODE="${4:-${ASSEMBLER:-spades}}"
SPADES_MODE="${SPADES_MODE,,}"
case "$SPADES_MODE" in
  spades|metaspades) ;;
  *) log_error "SPADES_MODE invalido: '$SPADES_MODE'. Use spades ou metaspades." ;;
esac
if ! [[ "$THREADS" =~ ^[1-9][0-9]*$ ]]; then
  log_error "THREADS deve ser um inteiro positivo: '$THREADS'."
fi

# Forçar offset 33 para dados sintéticos do pipeline para evitar falhas do auto-detector
if [[ "$SAMPLE" == "DEMO" || "$SAMPLE" == "nohits" ]]; then
  if [[ " ${SPADES_PARAMS} " != *" --phred-offset "* ]]; then
    SPADES_PARAMS="${SPADES_PARAMS} --phred-offset 33"
  fi
fi

# Validar limite de memória do SPAdes contra a RAM total disponível no sistema
if [[ -f /proc/meminfo ]]; then
  mem_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
  ram_gb=$(( mem_kb / 1024 / 1024 ))
else
  ram_gb=16
fi

if [[ " ${SPADES_PARAMS} " =~ [[:space:]](-m|--memory)[[:space:]\=]([0-9]+) ]]; then
  spades_mem="${BASH_REMATCH[2]}"
  if (( spades_mem > ram_gb )); then
    safe_mem=$(( ram_gb * 80 / 100 ))
    if (( safe_mem < 4 )); then
      safe_mem=4
    fi
    SPADES_PARAMS=$(echo "${SPADES_PARAMS}" | sed -E "s/(-m|--memory)([[:space:]\=])${spades_mem}/\1\2${safe_mem}/")
    log_info "[WARN] SPAdes -m ${spades_mem} excede RAM disponível; ajustando para -m ${safe_mem}."
  fi
fi
read -r -a SPADES_ARGS <<< "$SPADES_PARAMS"

RAW_DIR="$(resolve_path "${RAW_DIR:-data/raw}")"
ASSEMBLY_DIR="$(resolve_path "${ASSEMBLY_DIR:-data/assemblies}")"

# SPAdes 4.x falha quando o caminho de output contém espaços
# Sanitizar: trocar espaços por _ no diretório de saída
SAFE_SAMPLE="${SAMPLE// /_}"
OUTDIR="${ASSEMBLY_DIR}/${SAFE_SAMPLE}_spades"
ORIG_OUTDIR="${ASSEMBLY_DIR}/${SAMPLE}_spades"

pick_first() { printf '%s\n' "$@" 2>/dev/null | sed '/^$/d' | sort | head -n1; }
find_read() {
  local sample="$1" raw_dir="$2" which="$3"
  local -a cands=()
  shopt -s nullglob
  if [[ "$which" == "R1" ]]; then
    cands=(
      "$raw_dir/${sample}_R1"*.fastq.gz "$raw_dir/${sample}_R1"*.fq.gz
      "$raw_dir/${sample}_R1"*.fastq    "$raw_dir/${sample}_R1"*.fq
      "$raw_dir/${sample}"*"_R1"*".fastq.gz" "$raw_dir/${sample}"*"_R1"*".fq.gz"
      "$raw_dir/${sample}"*"_R1"*".fastq"    "$raw_dir/${sample}"*"_R1"*".fq"
      "$raw_dir/${sample}_1"*.fastq.gz "$raw_dir/${sample}_1"*.fq.gz
      "$raw_dir/${sample}_1"*.fastq    "$raw_dir/${sample}_1"*.fq
    )
  else
    cands=(
      "$raw_dir/${sample}_R2"*.fastq.gz "$raw_dir/${sample}_R2"*.fq.gz
      "$raw_dir/${sample}_R2"*.fastq    "$raw_dir/${sample}_R2"*.fq
      "$raw_dir/${sample}"*"_R2"*".fastq.gz" "$raw_dir/${sample}"*"_R2"*".fq.gz"
      "$raw_dir/${sample}"*"_R2"*".fastq"    "$raw_dir/${sample}"*"_R2"*".fq"
      "$raw_dir/${sample}_2"*.fastq.gz "$raw_dir/${sample}_2"*.fq.gz
      "$raw_dir/${sample}_2"*.fastq    "$raw_dir/${sample}_2"*.fq
    )
  fi
  shopt -u nullglob
  pick_first "${cands[@]}"
}
# Prioridade: SINGLE explícito -> env R1/R2 -> auto-detect em RAW_DIR
RAW_SINGLE="${SAMPLE_SINGLE:-${SINGLE:-${FASTQ_SINGLE:-}}}"
RAW1="${R1:-${READ1:-${FASTQ_R1:-}}}"
RAW2="${R2:-${READ2:-${FASTQ_R2:-}}}"

if [[ -n "$RAW_SINGLE" && ( -n "$RAW1" || -n "$RAW2" ) ]]; then
  log_error "Use entrada single-end ou paired-end, nunca ambas."
fi
if [[ -n "${RAW_SINGLE}" ]]; then
  RAW_SINGLE="$(resolve_path "$RAW_SINGLE")"
  if [[ "$SPADES_MODE" == "metaspades" ]]; then
    log_error "metaSPAdes requer uma biblioteca curta paired-end; single-end nao e suportado."
  fi
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$RAW_SINGLE" >/dev/null || exit 2
else
  if [[ -n "$RAW1" || -n "$RAW2" ]]; then
    [[ -n "$RAW1" && -n "$RAW2" ]] || log_error "R1 e R2 devem ser informados juntos."
  else
    RAW1="$(find_read "$SAMPLE" "$RAW_DIR" "R1")"
    RAW2="$(find_read "$SAMPLE" "$RAW_DIR" "R2")"
  fi

  if [[ -z "${RAW1}" || -z "${RAW2}" ]]; then
    log_error "FASTQs não encontrados para sample='$SAMPLE'.
Procurei em: $RAW_DIR
Exemplos aceitos:
  ${SAMPLE}_R1*.fastq(.gz) / ${SAMPLE}_R2*.fastq(.gz)
  ${SAMPLE}_1*.fq(.gz)     / ${SAMPLE}_2*.fq(.gz)
Alternativa (recomendado):
  R1=/caminho/read1.fastq.gz R2=/caminho/read2.fastq.gz make pipeline SAMPLE=$SAMPLE
Para single-end:
  SAMPLE_SINGLE=/caminho/reads.fastq.gz make pipeline SAMPLE=$SAMPLE"
  fi
  RAW1="$(resolve_path "$RAW1")"
  RAW2="$(resolve_path "$RAW2")"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$RAW1" --mate "$RAW2" >/dev/null || exit 2
fi

command -v spades.py >/dev/null 2>&1 || log_error $'spades.py não encontrado no PATH.\nUbuntu/WSL: sudo apt update && sudo apt install -y spades'

log_info "[SPAdes] sample=$SAMPLE"
if [[ -n "${RAW_SINGLE}" ]]; then
  log_info "[SPAdes] SINGLE=$RAW_SINGLE"
else
  log_info "[SPAdes] R1=$RAW1"
  log_info "[SPAdes] R2=$RAW2"
fi
log_info "[SPAdes] mode=$SPADES_MODE threads=$THREADS params='$SPADES_PARAMS'"
META_FLAG=""
if [[ "$SPADES_MODE" == "metaspades" ]]; then
  if [[ " ${SPADES_PARAMS} " != *" --meta "* ]]; then
    META_FLAG="--meta"
  fi
fi
# Detectar caracteres problemáticos que quebram o PropertyTree do BayesHammer (spades-hammer)
HAMMER_BYPASS=""
if [[ "$OUTDIR" == *" "* || "$OUTDIR" == *"("* || "$OUTDIR" == *")"* ]]; then
  HAMMER_BYPASS="--only-assembler"
  log_info "[SPAdes] AVISO: Caminho de saída contém espaços ou parênteses. Forçando '--only-assembler' para evitar travamento do BayesHammer."
fi

# Criar ambiente temporário curto livre de espaços/parênteses para evitar bugs do spades.py
SPADES_TMP_DIR="/tmp/spades_tmp_$(date +%s)_$$"
mkdir -p "$SPADES_TMP_DIR"
SPADES_TMP_OUT="$SPADES_TMP_DIR/out"
SPADES_LOG_DIR="${GENEIN_WORK_ROOT:-$REPO_ROOT}/logs/assembly"
mkdir -p "$SPADES_LOG_DIR"
trap 'rm -rf "$SPADES_TMP_DIR"' EXIT

# Links simbólicos de entrada curtos
if [[ -n "${RAW_SINGLE}" ]]; then
  ln -sf "$(realpath "$RAW_SINGLE")" "$SPADES_TMP_DIR/s.fastq.gz"
  log_info "[SPAdes] Executando montagem via link curto: $SPADES_TMP_DIR/s.fastq.gz"
  spades.py \
    -s "$SPADES_TMP_DIR/s.fastq.gz" \
    -o "$SPADES_TMP_OUT" \
    -t "$THREADS" \
    $META_FLAG \
    ${HAMMER_BYPASS:-} \
    "${SPADES_ARGS[@]}"
else
  ln -sf "$(realpath "$RAW1")" "$SPADES_TMP_DIR/r1.fastq.gz"
  ln -sf "$(realpath "$RAW2")" "$SPADES_TMP_DIR/r2.fastq.gz"
  log_info "[SPAdes] Executando montagem via links curtos em $SPADES_TMP_DIR"
  spades.py \
    -1 "$SPADES_TMP_DIR/r1.fastq.gz" \
    -2 "$SPADES_TMP_DIR/r2.fastq.gz" \
    -o "$SPADES_TMP_OUT" \
    -t "$THREADS" \
    $META_FLAG \
    ${HAMMER_BYPASS:-} \
    "${SPADES_ARGS[@]}"
fi

# Validate this attempt, not a same-sample artifact left by an older run.
# spades.py already returned 0 here (set -e). A contigs.fasta that EXISTS and is
# EMPTY is a completed attempt with zero contigs: publish it empty so
# assembly_router.sh records SOFT. Missing or invalid output stays fatal.
EMPTY_ASSEMBLY=0
if [[ -f "$SPADES_TMP_OUT/contigs.fasta" && ! -s "$SPADES_TMP_OUT/contigs.fasta" ]]; then
  EMPTY_ASSEMBLY=1
  log_warn "[SPAdes] montagem concluida sem contigs (contigs.fasta presente e vazio); publicando FASTA vazio."
else
  check_file "$SPADES_TMP_OUT/contigs.fasta"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$SPADES_TMP_OUT/contigs.fasta" >/dev/null || \
    log_error "SPAdes gerou contigs.fasta invalido."
fi

# Publish FASTA artifacts atomically. A failed attempt leaves the last complete
# assembler output untouched, while the router will never attribute it to the
# failed attempt because it checks the child exit status first.
mkdir -p "$OUTDIR"
CONTIGS_TMP="$(mktemp "${OUTDIR}/.contigs.fasta.XXXXXX")"
cp -f "$SPADES_TMP_OUT/contigs.fasta" "$CONTIGS_TMP"
mv -f "$CONTIGS_TMP" "$OUTDIR/contigs.fasta"
if [[ -f "$SPADES_TMP_OUT/scaffolds.fasta" ]]; then
  SCAFFOLDS_TMP="$(mktemp "${OUTDIR}/.scaffolds.fasta.XXXXXX")"
  cp -f "$SPADES_TMP_OUT/scaffolds.fasta" "$SCAFFOLDS_TMP"
  mv -f "$SCAFFOLDS_TMP" "$OUTDIR/scaffolds.fasta"
fi
if [[ -f "$SPADES_TMP_OUT/spades.log" ]]; then
  SPADES_LOG_TMP="$(mktemp "${OUTDIR}/.spades.log.XXXXXX")"
  cp -f "$SPADES_TMP_OUT/spades.log" "$SPADES_LOG_TMP"
  mv -f "$SPADES_LOG_TMP" "$OUTDIR/spades.log"
fi

# Preservação de contigs por k-mer intermediários
if [[ "${FRAGMENT_HUNTER_KEEP_ALL_KMERS:-false}" == "true" ]]; then
  STD_ASM_DIR="${ASSEMBLY_DIR}/${SAMPLE}_assembly"
  KMERS_DIR="${STD_ASM_DIR}/kmers"
  mkdir -p "$KMERS_DIR"

  ALL_KMERS_FA="${STD_ASM_DIR}/all_kmers_contigs.fa"
  rm -f "$ALL_KMERS_FA"
  touch "$ALL_KMERS_FA"

  log_info "FRAGMENT_HUNTER_KEEP_ALL_KMERS=true: executando montagens single-k para recuperação de fragmentos."

  # Extrair lista de k-mers
  if [[ " ${SPADES_PARAMS} " =~ [[:space:]](-k|--kmer)[[:space:]\=]([0-9\,]+) ]]; then
    kmers_str="${BASH_REMATCH[2]}"
  else
    kmers_str="21,33,55,77"
  fi

  IFS=',' read -ra kmer_list <<< "$kmers_str"
  for k in "${kmer_list[@]}"; do
    log_info "Rodando SPAdes single-k K${k}..."

    # Substituir ou adicionar o k-mer atual
    if [[ " ${SPADES_PARAMS} " =~ [[:space:]](-k|--kmer)[[:space:]\=]([0-9\,]+) ]]; then
      SINGLE_K_PARAMS=$(echo "${SPADES_PARAMS}" | sed -E "s/(-k|--kmer)([[:space:]\=])[0-9\,]+/\1\2${k}/")
    else
      SINGLE_K_PARAMS="${SPADES_PARAMS} -k ${k}"
    fi
    read -r -a SINGLE_K_ARGS <<< "$SINGLE_K_PARAMS"

    # Criar pasta temporária single-k
    K_TMP_DIR="${SPADES_TMP_DIR}/single_k_${k}"
    mkdir -p "$K_TMP_DIR"
    K_TMP_OUT="${K_TMP_DIR}/out"

    # Executar spades single-k
    set +e
    K_STDOUT="${SPADES_LOG_DIR}/${SAFE_SAMPLE}_spades_K${k}.stdout.log"
    K_STDERR="${SPADES_LOG_DIR}/${SAFE_SAMPLE}_spades_K${k}.stderr.log"
    if [[ -n "${RAW_SINGLE}" ]]; then
      spades.py \
        -s "$SPADES_TMP_DIR/s.fastq.gz" \
        -o "$K_TMP_OUT" \
        -t "$THREADS" \
        $META_FLAG \
        ${HAMMER_BYPASS:-} \
        "${SINGLE_K_ARGS[@]}" > "$K_STDOUT" 2> "$K_STDERR"
    else
      spades.py \
        -1 "$SPADES_TMP_DIR/r1.fastq.gz" \
        -2 "$SPADES_TMP_DIR/r2.fastq.gz" \
        -o "$K_TMP_OUT" \
        -t "$THREADS" \
        $META_FLAG \
        ${HAMMER_BYPASS:-} \
        "${SINGLE_K_ARGS[@]}" > "$K_STDOUT" 2> "$K_STDERR"
    fi
    K_RC=$?
    set -e
    if [[ $K_RC -ne 0 ]]; then
      log_warn "K${k}: SPAdes single-k falhou com exit code ${K_RC}. Logs: stdout=${K_STDOUT}; stderr=${K_STDERR}"
    fi

    # Verificar se gerou contigs.fasta válido
    if [[ -s "${K_TMP_OUT}/contigs.fasta" ]]; then
      if head -n 1 "${K_TMP_OUT}/contigs.fasta" 2>/dev/null | grep -q "^>"; then
        target_kmer_fa="${KMERS_DIR}/K${k}_contigs.fa"
        cp -f "${K_TMP_OUT}/contigs.fasta" "$target_kmer_fa"
        log_info "K${k}: contigs salvos em data/assemblies/${SAMPLE}_assembly/kmers/K${k}_contigs.fa"

        # Renomear cabeçalhos no all_kmers_contigs.fa
        sed "s/^>/>${SAMPLE}|K${k}|/" "${K_TMP_OUT}/contigs.fasta" >> "$ALL_KMERS_FA"
      else
        log_warn "K${k}: montagem single-k não gerou contigs."
      fi
    else
      log_warn "K${k}: montagem single-k não gerou contigs."
    fi
  done
fi

[[ "$EMPTY_ASSEMBLY" -eq 1 ]] || check_file "$OUTDIR/contigs.fasta"

# Se o nome foi sanitizado (espaços), criar symlink para o nome original
if [[ "$SAFE_SAMPLE" != "$SAMPLE" && ! -e "$ORIG_OUTDIR" ]]; then
  if ! ln -sf "$OUTDIR" "$ORIG_OUTDIR" 2>/dev/null; then
    mkdir -p "$ORIG_OUTDIR"
    rm -f "$ORIG_OUTDIR/contigs.fasta"
    cp -f "$OUTDIR/contigs.fasta" "$ORIG_OUTDIR/contigs.fasta"
    log_info "[SPAdes] cp fallback: contigs copiados para $ORIG_OUTDIR"
  fi
fi

log_info "[SPAdes] OK: $OUTDIR/contigs.fasta"
