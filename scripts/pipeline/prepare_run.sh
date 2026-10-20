#!/usr/bin/env bash
# This module is sourced by run_sample.sh; its variables are consumed there.
# shellcheck disable=SC2034
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"
# The source tree remains read-only during externally isolated executions.
WORK_ROOT="${GENEIN_WORK_ROOT:-$REPO_ROOT}"
if [[ -n "${GENEIN_WORK_ROOT:-}" ]]; then
  [[ "$WORK_ROOT" == /* && -d "$WORK_ROOT" ]] || {
    echo "[FATAL] GENEIN_WORK_ROOT must be an existing absolute directory" >&2
    exit 2
  }
  WORK_ROOT="$(cd "$WORK_ROOT" && pwd)"
  export GENEIN_WORK_ROOT="$WORK_ROOT"
  cd "$WORK_ROOT"
fi
source "${SCRIPTS_ROOT}/lib/common.sh"
source "${SCRIPTS_ROOT}/lib/host_filter.sh"
# Normalize incoming DB if it has an alias
case "${DB:-}" in
  teschovirus_a|teschovirus)   DB="ptv" ;;
  enterovirus_g)               DB="evg" ;;
  sapelovirus_a)               DB="psv" ;;
  senecavirus_a)               DB="svv" ;;
  fmdv|foot_and_mouth)         DB="fmdv" ;;
esac

# Limpar preventivamente variáveis herdadas do ambiente que apontam para caminhos inexistentes
# ou que referenciem o diretório antigo do Gene-In (evitando quebras após clonar/renomear pastas).
for var in REF_FASTA BLAST_DB BOWTIE2_INDEX; do
  val="${!var:-}"
  if [[ -n "$val" ]]; then
    if [[ ! -e "$val" && "$val" == /* ]]; then
      shopt -s nullglob
      companions=("${val}".*)
      shopt -u nullglob
      if ((${#companions[@]} == 0)); then
        unset "$var"
      fi
    fi
  fi
done

# Configuração canônica: os nomes de variável abaixo são os únicos que
# scripts/pipeline/resolve_config.py precisa para reproduzir a prioridade já
# documentada (CLI > ambiente prévio ao `source` > config/picornavirus.env >
# padrão interno). Capturamos aqui apenas o retrato "antes"/"depois" de cada
# variável; quem interpreta config/picornavirus.env continua sendo o bash
# `source` — o resolvedor nunca lê o arquivo diretamente, então uma sintaxe
# shell mais elaborada nele continua funcionando exatamente como hoje.
TIER_A_CONFIG_VARS=(
  DB DB_QUERY BLAST_DB ASSEMBLER ANALYSIS_PROFILE
  HOST_FILTER_ENABLED HOST_NAME HOST_ACCESSION HOST_INDEX_PREFIX
  SHORT_FRAGMENT_MODE SHORT_FRAGMENT_MIN_LEN SHORT_FRAGMENT_MAX_LEN SHORT_FRAGMENT_DEDUP
  SHORT_FRAGMENT_BLAST SHORT_FRAGMENT_WORD_SIZE SHORT_FRAGMENT_EVALUE
  SHORT_FRAGMENT_MIN_PID SHORT_FRAGMENT_MIN_QCOV
  EVIDENCE_V2 EVIDENCE_PROFILES EVIDENCE_ROOT EVIDENCE_LIBRARY_MODE EVIDENCE_UMI_MODE
  EVIDENCE_ROLE EVIDENCE_EXPECTED_TARGET EVIDENCE_COMPOSITE_DB EVIDENCE_SUBJECT_LABELS
  EVIDENCE_PANEL_FASTA EVIDENCE_PANEL_INDEX EVIDENCE_RUN_ID EVIDENCE_BATCH_ID
  EVIDENCE_RESERVATION_TOKEN
  SEARCH_PROFILES
  QC_ADAPTER_R1 QC_ADAPTER_R2
)
TIER_B_CONFIG_VARS=(
  VELVET_K THREADS SPADES_PARAMS ADVANCED_KMERS BLAST_TASK BLAST_WORD_SIZE BLAST_EVALUE CONTIGS
  RAW_DIR QC_OUT_DIR QC_REPORT_DIR HOST_REMOVED_DIR SAMPLE_R1 SAMPLE_R2 SAMPLE_SINGLE
)
RESOLVE_CONFIG_INCOMING_ARGS=()
for var in "${TIER_A_CONFIG_VARS[@]}"; do
  RESOLVE_CONFIG_INCOMING_ARGS+=(--incoming "${var}=${!var:-}")
done

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
LEGACY_CONFIG="${REPO_ROOT}/config.env"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

RESOLVE_CONFIG_SOURCED_ARGS=()
for var in "${TIER_A_CONFIG_VARS[@]}" "${TIER_B_CONFIG_VARS[@]}"; do
  RESOLVE_CONFIG_SOURCED_ARGS+=(--sourced "${var}=${!var:-}")
done
: "${HOST_MIN_ALIGNMENT_RATE:=50}"
: "${QC_MIN_LEN:=20}"
: "${QC_MIN_QUAL:=20}"
ANALYSIS_PROFILES_CONFIG="${ANALYSIS_PROFILES_CONFIG:-${REPO_ROOT}/config/analysis_profiles.json}"
# scripts/evidence/run_batch.sh (fora do escopo desta mudança) é acionado
# antes do resolvedor rodar, então precisa dos mesmos padrões aqui; a
# resolução completa (com override de CLI) roda mais abaixo para o caminho
# de amostra única.
EVIDENCE_PROFILES="${EVIDENCE_PROFILES:-${REPO_ROOT}/config/evidence_profiles.json}"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-${REPO_ROOT}/results/evidence}"
usage() {
  cat <<'USAGE'
Uso: scripts/pipeline/run.sh [opções]
Opções:
  --install                 instala dependências via apt-get (usa scripts/ops/check_env.sh)
  --sample NOME             nome da amostra (obrigatório se SAMPLE_ID/SAMPLE_NAME/SAMPLE não estiver definido)
  --r1 ARQUIVO              FASTQ paired-end, primeiro mate (exige --r2)
  --r2 ARQUIVO              FASTQ paired-end, segundo mate
  --single ARQUIVO          FASTQ single-end
  --kmer K                  k-mer para Velvet (padrão: VELVET_K ou 31)
  --analysis-profile NOME   perfil: default ou assembly-consensus
  --assembler NOME          montador manual: velvet, spades ou metaspades
  --threads N               número de threads (padrão: THREADS ou 4)
  --spades-params "PARAMS"  parâmetros extras para SPAdes/metaSPAdes
  --advanced-kmers LISTA    k-mers manuais, impares/crescentes e menores que as reads
  --blast-task NOME         tarefa BLAST: blastn ou blastn-short
  --blast-word-size N       word size do BLAST
  --blast-evalue VALOR      e-value do BLAST
  --contigs ARQUIVO         usa contigs já montados como entrada (ignora montagem)
  --search-profiles LISTA   perfis de busca explícitos (A, B, C ou combinação: "A,C").
                            Padrão: apenas A (contigs vs BLAST_DB) — B e C só rodam se pedidos.
  --skip-assembly           ignora a etapa de montagem (exige --contigs)
  --skip-host-filter        ignora o filtro do hospedeiro
  --host-expected true|false  indica se a presenca do hospedeiro declarado
                            e esperada nesta amostra. true (padrao quando
                            omitido, retrocompativel) mantem o alarme de taxa
                            minima de alinhamento; false permite taxa baixa
                            com aviso, sem abortar. A saturacao total pelo
                            hospedeiro (nenhuma leitura sobrevive) e sempre
                            um desfecho estruturado, independente desta opcao.
  --skip-qc                 ignora o controle de qualidade com fastp
  --rescue-mode             força o resgate de reads se a montagem falhar ou contigs forem muito curtos
  --evidence-v2             gera artefatos de análise de evidência
  --evidence-profiles ARQ   catálogo JSON de perfis científicos Evidence 2.0
  --evidence-root DIR       raiz unica para staging, estado e runs Evidence 2.0
  --batch-manifest TSV      executa um lote pelo orquestrador Python
  -h, --help                mostra esta ajuda
Prioridade de configuração:
  1. argumentos da linha de comando
  2. variáveis de ambiente / config.env
  3. padrões internos seguros
Obs.: picornavirus.env no diretório de trabalho (ou config.env legado) é a base de configuração. O painel não grava esse arquivo dentro da fonte.
USAGE
}
resolve_path() {
  local path="$1"
  if [[ "$path" == /* ]]; then
    echo "$path"
  else
    echo "${REPO_ROOT}/${path}"
  fi
}
require_value() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" ]]; then
    echo "[ERRO] valor ausente para $opt" >&2
    usage
    exit 1
  fi
}
log() {
  printf '\n== [%s] %s ==\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$1"
}
AUTO_INSTALL=0
SKIP_HOST_FILTER=0
SKIP_QC=0
RESCUE_MODE=0
SAMPLE_OVERRIDE=""
SAMPLE_R1_OVERRIDE=""
SAMPLE_R2_OVERRIDE=""
SAMPLE_SINGLE_OVERRIDE=""
KMER_OVERRIDE=""
ASSEMBLER_OVERRIDE=""
ANALYSIS_PROFILE_OVERRIDE=""
THREADS_OVERRIDE=""
SPADES_PARAMS_OVERRIDE=""
ADVANCED_KMERS_OVERRIDE=""
BLAST_TASK_OVERRIDE=""
BLAST_WORD_SIZE_OVERRIDE=""
BLAST_EVALUE_OVERRIDE=""
CONTIGS_OVERRIDE=""
SEARCH_PROFILES_OVERRIDE=""
EVIDENCE_V2_OVERRIDE=""
EVIDENCE_PROFILES_OVERRIDE=""
EVIDENCE_ROOT_OVERRIDE=""
BATCH_MANIFEST=""
SKIP_ASSEMBLY=0
HOST_EXPECTED_OVERRIDE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      AUTO_INSTALL=1
      shift
      ;;
    --sample)
      require_value "$1" "${2:-}"
      SAMPLE_OVERRIDE="$2"
      shift 2
      ;;
    --r1)
      require_value "$1" "${2:-}"
      SAMPLE_R1_OVERRIDE="$2"
      shift 2
      ;;
    --r2)
      require_value "$1" "${2:-}"
      SAMPLE_R2_OVERRIDE="$2"
      shift 2
      ;;
    --single)
      require_value "$1" "${2:-}"
      SAMPLE_SINGLE_OVERRIDE="$2"
      shift 2
      ;;
    --kmer)
      require_value "$1" "${2:-}"
      KMER_OVERRIDE="$2"
      shift 2
      ;;
    --assembler)
      require_value "$1" "${2:-}"
      ASSEMBLER_OVERRIDE="$2"
      shift 2
      ;;
    --analysis-profile)
      require_value "$1" "${2:-}"
      ANALYSIS_PROFILE_OVERRIDE="$2"
      shift 2
      ;;
    --threads)
      require_value "$1" "${2:-}"
      THREADS_OVERRIDE="$2"
      shift 2
      ;;
    --spades-params)
      require_value "$1" "${2:-}"
      SPADES_PARAMS_OVERRIDE="$2"
      shift 2
      ;;
    --blast-task)
      require_value "$1" "${2:-}"
      BLAST_TASK_OVERRIDE="$2"
      shift 2
      ;;
    --advanced-kmers)
      require_value "$1" "${2:-}"
      ADVANCED_KMERS_OVERRIDE="$2"
      shift 2
      ;;
    --blast-word-size)
      require_value "$1" "${2:-}"
      BLAST_WORD_SIZE_OVERRIDE="$2"
      shift 2
      ;;
    --blast-evalue)
      require_value "$1" "${2:-}"
      BLAST_EVALUE_OVERRIDE="$2"
      shift 2
      ;;
    --contigs)
      require_value "$1" "${2:-}"
      CONTIGS_OVERRIDE="$2"
      shift 2
      ;;
    --search-profiles)
      require_value "$1" "${2:-}"
      SEARCH_PROFILES_OVERRIDE="$2"
      shift 2
      ;;
    --skip-assembly)
      SKIP_ASSEMBLY=1
      shift
      ;;
    --skip-host-filter)
      SKIP_HOST_FILTER=1
      shift
      ;;
    --host-expected)
      require_value "$1" "${2:-}"
      case "${2,,}" in
        true|1|yes|sim) HOST_EXPECTED_OVERRIDE=true ;;
        false|0|no|nao) HOST_EXPECTED_OVERRIDE=false ;;
        *)
          echo "[ERRO] --host-expected invalido: '$2' — use true/false (ou 1/0, yes/no, sim/nao)." >&2
          exit 1
          ;;
      esac
      shift 2
      ;;
    --skip-qc)
      SKIP_QC=1
      shift
      ;;
    --rescue-mode)
      RESCUE_MODE=1
      shift
      ;;
    --evidence-v2)
      EVIDENCE_V2_OVERRIDE=true
      shift
      ;;
    --evidence-profiles)
      require_value "$1" "${2:-}"
      EVIDENCE_PROFILES_OVERRIDE="$2"
      EVIDENCE_PROFILES="$2"
      shift 2
      ;;
    --evidence-root)
      require_value "$1" "${2:-}"
      EVIDENCE_ROOT_OVERRIDE="$2"
      EVIDENCE_ROOT="$2"
      shift 2
      ;;
    --batch-manifest)
      require_value "$1" "${2:-}"
      BATCH_MANIFEST="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERRO] opção inválida: $1" >&2
      usage
      exit 1
      ;;
  esac
done

# --host-expected segue exatamente o mesmo contrato leve de repasse que
# HOST_MIN_ALIGNMENT_RATE (variavel de ambiente com default no proprio
# filter_host.sh, sem passar pelo resolvedor JSON): a interface publica é
# apenas esta flag; a ausência dela deixa HOST_EXPECTED sem valor aqui, e o
# comportamento retrocompatível (taxa baixa aborta) permanece o default de
# scripts/pipeline/filter_host.sh, sem alteração.
if [[ -n "$HOST_EXPECTED_OVERRIDE" ]]; then
  HOST_EXPECTED="$HOST_EXPECTED_OVERRIDE"
fi
export HOST_EXPECTED
