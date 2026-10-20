#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

# Normalize incoming DB if it has an alias
case "${DB:-}" in
  teschovirus_a|teschovirus)   DB="ptv" ;;
  enterovirus_g)               DB="evg" ;;
  sapelovirus_a)               DB="psv" ;;
  senecavirus_a)               DB="svv" ;;
  fmdv|foot_and_mouth)         DB="fmdv" ;;
esac

# 1. GUARDA AS VARIÁVEIS DO DASHBOARD (Prioridade Máxima)
INCOMING_DB="${DB:-}"
INCOMING_DB_QUERY="${DB_QUERY:-}"
CONFIG_FILE="${REPO_ROOT}/config/picornavirus.env"
LEGACY_CONFIG="${REPO_ROOT}/config.env"
if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
elif [[ -f "${LEGACY_CONFIG}" ]]; then
  # shellcheck disable=SC1090
  source "${LEGACY_CONFIG}"
fi

# 2. RESTAURA AS VARIÁVEIS (Sobrescrevendo o config.env)
if [[ -n "$INCOMING_DB_QUERY" && ( -z "$INCOMING_DB" || "$INCOMING_DB" == "custom" ) ]]; then
  # PRIORIDADE MÁXIMA: Query customizada
  DB_QUERY="$INCOMING_DB_QUERY"
  DB="custom"
  unset REF_FASTA BLAST_DB BOWTIE2_INDEX

  # O cache e a reconstrução serão controlados pelo validador de cache na etapa setup
elif [[ -n "$INCOMING_DB" ]]; then
  # PRIORIDADE SECUNDÁRIA: Lista suspensa
  DB="$INCOMING_DB"
  unset REF_FASTA BLAST_DB BOWTIE2_INDEX DB_QUERY
fi

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/common.sh"

mkdir -p "${REPO_ROOT}/tmp"
if [[ "${DB_MANAGER_LOCK_HELD:-0}" != "1" ]]; then
  exec 9>"${REPO_ROOT}/tmp/db-manager.lock"
  flock -x 9
fi
trap 'rm -f "${REF_TMP:-}" "${NORMALIZED_FASTA:-}"' EXIT

declare -A DB_QUERIES
declare -A DB_DESC

init_profiles() {
   DB_QUERIES[ptv]='"Teschovirus"[Organism]'
   DB_DESC[ptv]='Porcine teschovirus (Teschovirus)'

   DB_QUERIES[evg]='"Enterovirus G"[Organism]'
   DB_DESC[evg]='Enterovirus G (suínos)'

   DB_QUERIES[psv]='"Sapelovirus A"[Organism]'
   DB_DESC[psv]='Sapelovirus A (porcine sapelovirus)'

   DB_QUERIES[svv]='"Senecavirus A"[Organism]'
   DB_DESC[svv]='Senecavirus A'

   DB_QUERIES[fmdv]='"Foot-and-mouth disease virus"[Organism]'
   DB_DESC[fmdv]='FMDV (aftosa)'

   # >>> ASTROVIRUS ADICIONADO AQUI <<<
   DB_QUERIES[astrovirus_suino]='"porcine astrovirus"[Organism] OR "Mamastrovirus 3"[Organism]'
   DB_DESC[astrovirus_suino]='Astrovirus Suíno (Mamastrovirus 3)'

   DB_QUERIES[picornaviridae_refseq]='"Picornaviridae"[Organism] AND refseq[filter]'
   DB_DESC[picornaviridae_refseq]='Picornaviridae (RefSeq) [recomendado]'

   DB_QUERIES[picornaviridae_complete]='"Picornaviridae"[Organism] AND ("complete genome"[Title] OR "complete cds"[Title])'
   DB_DESC[picornaviridae_complete]='Picornaviridae (complete genome/cds)'

   DB_QUERIES[picornaviridae_all]='"Picornaviridae"[Organism]'
   DB_DESC[picornaviridae_all]='Picornaviridae (ALL) [gigante]'

   DB_QUERIES[picornaviridae]='"Picornaviridae"[Organism]'
   DB_DESC[picornaviridae]='TODOS Picornaviridae (alias antigo)'
}

usage() {
  cat <<'USAGE'
Uso: scripts/ops/db_manager.sh <comando>

Comandos:
  list   lista perfis básicos suportados (DB -> query NCBI)
  setup  baixa FASTA + gera BLAST DB + índice Bowtie2

Variáveis (env):
  DB             (padrão: ptv)
  DB_QUERY       (se definido, sobrescreve a query padrão do perfil)
  NCBI_DB        (padrão: nucleotide)

  REF_FASTA      (padrão: data/ref/<DB>.fa)
  BLAST_DB       (padrão: blastdb/<DB>)
  BOWTIE2_INDEX  (padrão: bowtie2/<DB>)

Exemplos — alvos pré-configurados:
  scripts/ops/db_manager.sh list
  DB=evg scripts/ops/db_manager.sh setup
  DB=picornaviridae_refseq scripts/ops/db_manager.sh setup

Exemplos — banco customizado (qualquer vírus via query NCBI):
  DB=custom DB_QUERY='"Orbivirus"[Organism]' scripts/ops/db_manager.sh setup
  DB=custom DB_QUERY='"Rotavirus A"[Organism]' scripts/ops/db_manager.sh setup
  DB=custom DB_QUERY='"Canine coronavirus"[Organism]' scripts/ops/db_manager.sh setup
  DB=custom DB_QUERY='"Picobirnavirus"[Organism]' scripts/ops/db_manager.sh setup
  DB=custom DB_QUERY='"Porcine kobuvirus"[All Fields]' scripts/ops/db_manager.sh setup

  Saídas do banco customizado:
    data/ref/custom.fa
    blastdb/custom.*
    bowtie2/custom.*
USAGE
}


init_profiles

CMD="${1:-}"
SETUP_BOWTIE2=1
case "$CMD" in
  list)
      # Ordem estável (não depende da ordem do associative array)
      DB_ORDER=(
        ptv evg psv svv fmdv astrovirus_suino
        picornaviridae_refseq picornaviridae_complete picornaviridae_all
      )

      if [[ "${2:-}" == "--json" ]]; then
        printf '[
'
        first=1
        for id in "${DB_ORDER[@]}"; do
          q="${DB_QUERIES[$id]:-}"
          d="${DB_DESC[$id]:-}"
          [[ -n "$q" ]] || continue

          # escape básico pra JSON
          q_esc="${q//\\/\\\\}"
          q_esc="${q_esc//\"/\\\"}"
          d_esc="${d//\\/\\\\}"
          d_esc="${d_esc//\"/\\\"}"

          if [[ $first -eq 0 ]]; then printf ',
'; fi
          first=0
          printf '  {"id":"%s","label":"%s","query":"%s"}' "$id" "$d_esc" "$q_esc"
        done
        printf '
]
'
        exit 0
      fi

      printf "DB	Desc	Query
"
      for id in "${DB_ORDER[@]}"; do
        q="${DB_QUERIES[$id]:-}"
        d="${DB_DESC[$id]:-}"
        [[ -n "$q" ]] || continue
        printf "%s	%s	%s
" "$id" "$d" "$q"
      done
      exit 0
      ;;

  setup)
    ;;
  setup-blast)
    SETUP_BOWTIE2=0
    ;;
  -h|--help|"")
    usage
    exit 0
    ;;
  *)
    usage
    exit 1
    ;;
esac

DB="${DB:-custom}"
NCBI_DB="${NCBI_DB:-nucleotide}"

# Alias resolution moved to top of the script

DEFAULT_QUERY="${DB_QUERIES[$DB]:-}"
DB_QUERY="${DB_QUERY:-$DEFAULT_QUERY}"
REFRESH_CUSTOM=0

bowtie2_index_complete() {
  local prefix="$1"
  local ext suffix
  for ext in bt2 bt2l; do
    for suffix in 1 2 3 4 rev.1 rev.2; do
      [[ -s "${prefix}.${suffix}.${ext}" ]] || break
    done
    if [[ "$suffix" == "rev.2" ]]; then
      return 0
    fi
  done
  return 1
}

if [[ -z "${DB_QUERY}" ]]; then
  log_error "DB_QUERY vazio e DB '${DB}' não tem perfil conhecido. Use DB_QUERY=... ou DB=ptv/evg/psv/svv/fmdv/picornaviridae_refseq/picornaviridae_complete/picornaviridae_all."
fi

REF_FASTA="$(resolve_path "${REF_FASTA:-data/ref/${DB}.fa}")"
BLAST_DB="$(resolve_path "${BLAST_DB:-blastdb/${DB}}")"
BOWTIE2_INDEX="$(resolve_path "${BOWTIE2_INDEX:-bowtie2/${DB}}")"
INDEX_MANIFEST="${BLAST_DB}.index-manifest.json"
BLAST_GENERATION_MANIFEST="${BLAST_DB}.db-manifest.json"
INDEX_CACHE_HELPER="${SCRIPTS_ROOT}/evidence/index_cache.py"
BLAST_PROMOTION_HELPER="${SCRIPTS_ROOT}/evidence/promote_blast_database.py"

blast_database_complete() {
  command -v blastdbcmd >/dev/null 2>&1 || return 1
  validate_blast_database "$BLAST_DB"
}

if [[ "$DB" == "custom" ]]; then
  METADATA_DIR="${REPO_ROOT}/db/custom"
  METADATA_FILE="${METADATA_DIR}/metadata.json"

  cache_valid=1
  if [[ -s "${REPO_ROOT}/data/ref/custom.fa" && -f "$METADATA_FILE" ]] && \
      blast_database_complete && bowtie2_index_complete "${REPO_ROOT}/bowtie2/custom"; then

    if METADATA_FILE="$METADATA_FILE" TARGET_QUERY="$DB_QUERY" TARGET_NCBI_DB="${NCBI_DB:-nucleotide}" python3 -c '
import json, os, sys
try:
    with open(os.environ["METADATA_FILE"], "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("db") != "custom":
        sys.exit(1)
    if data.get("db_query") != os.environ.get("TARGET_QUERY"):
        sys.exit(1)
    if data.get("ncbi_db") != os.environ.get("TARGET_NCBI_DB"):
        sys.exit(1)
    sys.exit(0)
except Exception:
    sys.exit(1)
' 2>/dev/null; then
      cache_valid=0
    fi
  fi

  if [[ $cache_valid -eq 0 ]] && python3 "$INDEX_CACHE_HELPER" \
      --manifest "$INDEX_MANIFEST" --reference "$REF_FASTA" \
      --builder makeblastdb --builder bowtie2-build; then
    log_info "Banco customizado existente compatível com a query atual. Reutilizando cache."
    log_info "OK (DB=${DB})"
    exit 0
  else
    log_info "Reconstruindo banco customizado (query nova, NCBI_DB diferente ou arquivos ausentes/vazios)."
    # Preserve the previous cache until the replacement FASTA and indexes
    REFRESH_CUSTOM=1
    # have been built and validated successfully.
  fi
fi

mkdir -p "$(dirname "$REF_FASTA")" "$(dirname "$BLAST_DB")" "$(dirname "$BOWTIE2_INDEX")"

if [[ ! -s "$REF_FASTA" || "$REFRESH_CUSTOM" -eq 1 ]]; then
  if ! command -v esearch >/dev/null 2>&1 || ! command -v efetch >/dev/null 2>&1; then
    log_error $'EDirect não encontrado (esearch/efetch).\n`esearch` e `efetch` fazem parte do pacote EDirect.\nNo Ubuntu/WSL, instale com:\n  sudo apt update && sudo apt install -y ncbi-entrez-direct\nAlternativa: forneça um FASTA local em REF_FASTA (ex.: REF_FASTA=data/ref/'"${DB}"'.fa) e rode novamente.'
  fi
  log_info "Baixando FASTA (NCBI_DB=${NCBI_DB}; DB_QUERY=${DB_QUERY})..."
  REF_TMP="${REF_FASTA}.download.$$"
  rm -f "$REF_TMP"
  if ! fetch_ncbi_fasta "$REF_TMP" "$NCBI_DB" "$DB_QUERY"; then
    log_error "Download NCBI falhou apos ${EDIRECT_RETRIES:-3} tentativa(s). O FASTA anterior foi preservado; revise a conectividade TLS, a query e tente novamente. Alternativa: forneca um FASTA local em REF_FASTA."
  fi
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$REF_TMP"
  mv -f "$REF_TMP" "$REF_FASTA"
  if [[ ! -s "$REF_FASTA" ]]; then
    log_error "Download falhou, FASTA vazio: $REF_FASTA"
  fi
else
  log_info "FASTA já existe: $REF_FASTA"
fi

blast_missing=0
blast_database_complete || blast_missing=1
if [[ $blast_missing -eq 0 ]] && ! python3 "$INDEX_CACHE_HELPER" \
    --manifest "$INDEX_MANIFEST" --reference "$REF_FASTA" --builder makeblastdb; then
  blast_missing=1
fi

if [[ $blast_missing -eq 1 ]]; then
  command -v makeblastdb >/dev/null 2>&1 || log_error "makeblastdb não encontrado (blast+)."
  command -v blastdbcmd >/dev/null 2>&1 || log_error "blastdbcmd não encontrado (blast+)."
  command -v blastdb_aliastool >/dev/null 2>&1 || log_error "blastdb_aliastool não encontrado (blast+)."
  log_info "Gerando BLAST DB em $BLAST_DB"
  # Remove taxid info from headers to prevent "taxid2offset error for tax id 0"
  DB_INPUT_FASTA="$REF_FASTA"
  NORMALIZED_FASTA=""
  if grep -q '|taxid|[0-9]' "$REF_FASTA"; then
    NORMALIZED_FASTA="${REF_FASTA}.normalized.$$"
    sed 's/|taxid|[0-9]*//g' "$REF_FASTA" > "$NORMALIZED_FASTA"
    python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$NORMALIZED_FASTA"
    DB_INPUT_FASTA="$NORMALIZED_FASTA"
  fi
  BLAST_PARENT="$(dirname "$BLAST_DB")"
  BLAST_BASENAME="$(basename "$BLAST_DB")"
  BLAST_BUILD_DIR="$(mktemp -d "${BLAST_PARENT}/.${BLAST_BASENAME}.build.XXXXXX")"
  BLAST_TMP_PREFIX="${BLAST_BUILD_DIR}/${BLAST_BASENAME}"
  [[ -n "$BLAST_TMP_PREFIX" && "$BLAST_TMP_PREFIX" != "/" ]] || \
    log_error "Prefixo de saída BLAST vazio; BLAST_DB=${BLAST_DB}, BLAST_BUILD_DIR=${BLAST_BUILD_DIR}"
  log_info "Executando makeblastdb com saída: ${BLAST_TMP_PREFIX}"
  MAKEBLASTDB_BIN="$(command -v makeblastdb)"
  [[ -x "$MAKEBLASTDB_BIN" ]] || log_error "makeblastdb não executável: ${MAKEBLASTDB_BIN:-indisponível}"
  # BLAST+ reparses filenames internally; shell quoting alone does not make
  # makeblastdb support output paths containing spaces. Build outside the
  # project path, then copy into same-filesystem staging for atomic promotion.
  (
    set -e
    BLAST_SAFE_DIR="$(mktemp -d /tmp/genein-makeblastdb.XXXXXX)"
    trap 'rm -f -- "$BLAST_SAFE_DIR"/"$BLAST_BASENAME".*; rmdir -- "$BLAST_SAFE_DIR"' EXIT
    "$MAKEBLASTDB_BIN" -in - -title "$BLAST_BASENAME" -dbtype nucl \
      -out "$BLAST_SAFE_DIR/$BLAST_BASENAME" < "$DB_INPUT_FASTA"
    blastdbcmd -db "$BLAST_SAFE_DIR/$BLAST_BASENAME" -info >/dev/null
    for index_file in "$BLAST_SAFE_DIR"/"$BLAST_BASENAME".*; do
      cp -- "$index_file" "$BLAST_BUILD_DIR/"
    done
  )
  validate_blast_database "$BLAST_TMP_PREFIX"
  BLAST_INDEX_MANIFEST_TMP="${BLAST_BUILD_DIR}/index-cache.json"
  python3 "$INDEX_CACHE_HELPER" --write --manifest "$BLAST_INDEX_MANIFEST_TMP" \
    --reference "$REF_FASTA" --builder makeblastdb
  python3 "$BLAST_PROMOTION_HELPER" --build-dir "$BLAST_BUILD_DIR" \
    --destination "$BLAST_DB" --reference "$REF_FASTA" --manifest "$BLAST_GENERATION_MANIFEST" \
    --index-manifest-source "$BLAST_INDEX_MANIFEST_TMP"
  BLAST_BUILD_DIR=""
  [[ -z "$NORMALIZED_FASTA" ]] || rm -f "$NORMALIZED_FASTA"
else
  log_info "BLAST DB atualizado: $BLAST_DB"
fi

if [[ "$SETUP_BOWTIE2" -eq 0 ]]; then
  log_info "Indice Bowtie2 omitido por solicitacao (setup-blast)."
  log_info "OK (DB=${DB})"
  exit 0
fi

bt2_missing=0
BT2_EXT="bt2"
if [[ -s "${BOWTIE2_INDEX}.1.bt2l" && -s "${BOWTIE2_INDEX}.2.bt2l" && \
      -s "${BOWTIE2_INDEX}.rev.1.bt2l" && -s "${BOWTIE2_INDEX}.rev.2.bt2l" ]]; then
  BT2_EXT="bt2l"
fi
bt2_files=(
  "${BOWTIE2_INDEX}.1.${BT2_EXT}"
  "${BOWTIE2_INDEX}.2.${BT2_EXT}"
  "${BOWTIE2_INDEX}.3.${BT2_EXT}"
  "${BOWTIE2_INDEX}.4.${BT2_EXT}"
  "${BOWTIE2_INDEX}.rev.1.${BT2_EXT}"
  "${BOWTIE2_INDEX}.rev.2.${BT2_EXT}"
)
for file in "${bt2_files[@]}"; do
  if [[ ! -s "$file" ]]; then
    bt2_missing=1
  fi
done
if [[ $bt2_missing -eq 0 ]] && ! python3 "$INDEX_CACHE_HELPER" \
    --manifest "$INDEX_MANIFEST" --reference "$REF_FASTA" \
    --builder makeblastdb --builder bowtie2-build; then
  bt2_missing=1
fi

if [[ $bt2_missing -eq 1 ]]; then
  command -v bowtie2-build >/dev/null 2>&1 || log_error "bowtie2-build não encontrado."
  log_info "Gerando índice Bowtie2 em $BOWTIE2_INDEX"
  BT2_TMP_PREFIX="${BOWTIE2_INDEX}.tmp.$$"
  rm -f "${BT2_TMP_PREFIX}"*.bt2 "${BT2_TMP_PREFIX}"*.bt2l
  bowtie2-build "$REF_FASTA" "$BT2_TMP_PREFIX"
  BUILD_EXT=""
  if [[ -s "${BT2_TMP_PREFIX}.1.bt2l" && -s "${BT2_TMP_PREFIX}.2.bt2l" &&
        -s "${BT2_TMP_PREFIX}.3.bt2l" && -s "${BT2_TMP_PREFIX}.4.bt2l" &&
        -s "${BT2_TMP_PREFIX}.rev.1.bt2l" && -s "${BT2_TMP_PREFIX}.rev.2.bt2l" ]]; then
    BUILD_EXT="bt2l"
  elif [[ -s "${BT2_TMP_PREFIX}.1.bt2" && -s "${BT2_TMP_PREFIX}.2.bt2" &&
          -s "${BT2_TMP_PREFIX}.3.bt2" && -s "${BT2_TMP_PREFIX}.4.bt2" &&
          -s "${BT2_TMP_PREFIX}.rev.1.bt2" && -s "${BT2_TMP_PREFIX}.rev.2.bt2" ]]; then
    BUILD_EXT="bt2"
  else
    log_error "Índice Bowtie2 temporário incompleto; o índice anterior foi preservado."
  fi
  for suffix in 1 2 3 4 rev.1 rev.2; do
    mv -f "${BT2_TMP_PREFIX}.${suffix}.${BUILD_EXT}" "${BOWTIE2_INDEX}.${suffix}.${BUILD_EXT}"
  done
  python3 "$INDEX_CACHE_HELPER" --write --manifest "$INDEX_MANIFEST" \
    --reference "$REF_FASTA" --builder makeblastdb --builder bowtie2-build
else
  log_info "Índice Bowtie2 atualizado: $BOWTIE2_INDEX"
fi

if [[ "$DB" == "custom" ]]; then
  METADATA_DIR="${REPO_ROOT}/db/custom"
  METADATA_FILE="${METADATA_DIR}/metadata.json"
  mkdir -p "$METADATA_DIR"
  METADATA_FILE="$METADATA_FILE" TARGET_QUERY="$DB_QUERY" TARGET_NCBI_DB="${NCBI_DB:-nucleotide}" INDEX_MANIFEST="$INDEX_MANIFEST" python3 -c '
import json, os, datetime
m = {
    "db": "custom",
    "db_query": os.environ.get("TARGET_QUERY"),
    "ncbi_db": os.environ.get("TARGET_NCBI_DB"),
    "ref_fasta": "data/ref/custom.fa",
    "blast_db": "blastdb/custom",
    "bowtie2_index": "bowtie2/custom",
    "index_manifest": os.environ.get("INDEX_MANIFEST"),
    "updated_at": datetime.datetime.now().isoformat()
}
with open(os.environ["METADATA_FILE"], "w", encoding="utf-8") as f:
    json.dump(m, f, indent=2, ensure_ascii=False)
'
  log_info "Metadata salvo em $METADATA_FILE"
fi

log_info "OK (DB=${DB})"
