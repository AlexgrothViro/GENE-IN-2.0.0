#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"
# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/common.sh"

usage() {
  cat <<'USAGE'
Uso:
  bash scripts/ops/build_viral_db.sh --target <key> [--query "<ncbi query>" | --taxid <id>]

Saída:
  db/<target>/
    sequences.fasta
    blastdb/
    metadata.json
USAGE
}

TARGET=""
QUERY=""
TAXID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    --query) QUERY="${2:-}"; shift 2 ;;
    --taxid) TAXID="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERRO] argumento inválido: $1"; usage; exit 2 ;;
  esac
done

[[ -n "$TARGET" ]] || log_error "Parâmetro obrigatório ausente: --target"
if [[ -n "$QUERY" && -n "$TAXID" ]]; then
  log_error "Use apenas um entre --query e --taxid"
fi

if ! command -v esearch >/dev/null 2>&1 || ! command -v efetch >/dev/null 2>&1; then
  log_error $'EDirect não encontrado (esearch/efetch).\n`esearch` e `efetch` fazem parte do pacote EDirect.\nNo Ubuntu/WSL, instale com:\n  sudo apt update && sudo apt install -y ncbi-entrez-direct'
fi
command -v makeblastdb >/dev/null 2>&1 || log_error "makeblastdb não encontrado (blast+)."

TARGETS_FILE="$REPO_ROOT/config/targets.json"
[[ -f "$TARGETS_FILE" ]] || log_error "Catálogo de alvos não encontrado: config/targets.json"

TARGET_JSON="$(python3 - "$TARGETS_FILE" "$TARGET" <<'PY'
import json,sys
path,key=sys.argv[1],sys.argv[2]
with open(path,encoding='utf-8') as fh:
    data=json.load(fh)
for item in data:
    if item.get('key')==key:
        print(json.dumps(item,ensure_ascii=False))
        break
PY
)"
[[ -n "$TARGET_JSON" ]] || log_error "Target '$TARGET' não encontrado em config/targets.json"

DEFAULT_QUERY="$(python3 - "$TARGET_JSON" <<'PY'
import json,sys
obj=json.loads(sys.argv[1])
print(obj.get('query_default') or '')
PY
)"
DEFAULT_TAXID="$(python3 - "$TARGET_JSON" <<'PY'
import json,sys
obj=json.loads(sys.argv[1])
print(obj.get('taxid') or '')
PY
)"

if [[ -z "$QUERY" && -n "$TAXID" ]]; then
  QUERY="txid${TAXID}[Organism:exp]"
fi
if [[ -z "$QUERY" && -z "$TAXID" && -n "$DEFAULT_TAXID" ]]; then
  TAXID="$DEFAULT_TAXID"
  QUERY="txid${TAXID}[Organism:exp]"
fi
if [[ -z "$QUERY" ]]; then
  QUERY="$DEFAULT_QUERY"
fi
[[ -n "$QUERY" ]] || log_error "Nenhuma query definida para o alvo '$TARGET'."

OUT_DIR="$REPO_ROOT/db/$TARGET"
FASTA="$OUT_DIR/sequences.fasta"
BLAST_DIR="$OUT_DIR/blastdb"
BLAST_PREFIX="$BLAST_DIR/$TARGET"
META="$OUT_DIR/metadata.json"
LOG_DIR="$REPO_ROOT/logs/db"
MAKEBLASTDB_OUT="$LOG_DIR/${TARGET}_makeblastdb.stdout.log"
MAKEBLASTDB_ERR="$LOG_DIR/${TARGET}_makeblastdb.stderr.log"

mkdir -p "$BLAST_DIR" "$LOG_DIR"

log_info "[DB] target=$TARGET"
log_info "[DB] query=$QUERY"
log_info "[DB] baixando sequências do NCBI..."

FASTA_TMP="${FASTA}.download.$$"
trap 'rm -f "$FASTA_TMP"' EXIT
if ! fetch_ncbi_fasta "$FASTA_TMP" nucleotide "$QUERY"; then
  log_error "Download NCBI falhou apos ${EDIRECT_RETRIES:-3} tentativa(s); o FASTA existente nao foi substituido. Revise a conectividade TLS e a query."
fi
python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$FASTA_TMP"
mv -f "$FASTA_TMP" "$FASTA"

SEQ_COUNT="$(grep -c '^>' "$FASTA" || true)"
if [[ "$SEQ_COUNT" -eq 0 ]]; then
  log_error "NCBI query retornou 0 sequências"
fi

log_info "[DB] sequências recuperadas: $SEQ_COUNT"
log_info "[DB] construindo BLAST DB..."
if ! makeblastdb -in "$FASTA" -dbtype nucl -out "$BLAST_PREFIX" -parse_seqids > "$MAKEBLASTDB_OUT" 2> "$MAKEBLASTDB_ERR"; then
  log_error "makeblastdb falhou para target '$TARGET'. Logs: stdout=${MAKEBLASTDB_OUT}; stderr=${MAKEBLASTDB_ERR}"
fi

EDIRECT_VERSION="$(esearch -version 2>/dev/null | head -n1 || true)"
[[ -n "$EDIRECT_VERSION" ]] || EDIRECT_VERSION="unknown"

python3 - "$META" "$TARGET_JSON" "$QUERY" "$TAXID" "$SEQ_COUNT" "$EDIRECT_VERSION" <<'PY'
import json,sys
meta_path,target_json,query,taxid,seq_count,version = sys.argv[1:7]
target=json.loads(target_json)
metadata={
    "target": target.get("key"),
    "display_name": target.get("display_name"),
    "query": query,
    "taxid": taxid or None,
    "date": __import__('datetime').datetime.utcnow().isoformat(timespec='seconds') + 'Z',
    "sequence_count": int(seq_count),
    "source": "NCBI Nucleotide (EDirect)",
    "version": version,
    "target_catalog": target,
}
with open(meta_path,'w',encoding='utf-8') as fh:
    json.dump(metadata,fh,indent=2,ensure_ascii=False)
PY

log_info "[DB] pronto: $OUT_DIR"
