#!/usr/bin/env bash
# =============================================================================
# blast_short_fragments.sh — BLAST sensível para fragmentos curtos
# =============================================================================
# Realiza blastn-short contra banco viral para fragmentos curtos extraídos
# pela etapa SHORT_FRAGMENT_MODE. Aplica filtros de identidade e cobertura
# de query. Gera resultados em results/blast/:
#   <sample>_short_fragments_blast.tsv    (hits brutos)
#   <sample>_short_fragments_filtered.tsv (após filtros pident/qcov)
#
# Uso direto:
#   bash scripts/pipeline/blast_short_fragments.sh \
#     --sample NOME --input FASTA --db CAMINHO_BLAST_DB \
#     [--word-size 7] [--evalue 1000] [--min-pid 70] [--min-qcov 70] \
#     [--threads 4]
#
# Ou via variáveis de ambiente exportadas pelo pipeline principal.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

# ---------------------------------------------------------------------------
# Defaults (sobrescritos por variáveis de ambiente ou argumentos CLI)
# ---------------------------------------------------------------------------
SAMPLE=""
INPUT_FASTA=""
BLAST_DB_PATH=""
WORD_SIZE="${SHORT_FRAGMENT_WORD_SIZE:-7}"
EVALUE="${SHORT_FRAGMENT_EVALUE:-1000}"
MIN_PID="${SHORT_FRAGMENT_MIN_PID:-70}"
MIN_QCOV="${SHORT_FRAGMENT_MIN_QCOV:-70}"
THREADS="${THREADS:-4}"
EVIDENCE_PROFILES="${EVIDENCE_PROFILES:-${REPO_ROOT}/config/evidence_profiles.json}"
EVIDENCE_ACTIVATION="${EVIDENCE_ACTIVATION:-${REPO_ROOT}/config/evidence_activation.json}"

# ---------------------------------------------------------------------------
# Parsing de argumentos
# ---------------------------------------------------------------------------
usage() {
  cat <<'USAGE'
Uso: scripts/pipeline/blast_short_fragments.sh [opções]
Opções:
  --sample   NOME         nome da amostra (obrigatório)
  --input    FASTA        FASTA de fragmentos curtos (obrigatório)
  --db       CAMINHO      caminho base do banco BLAST (sem extensão, obrigatório)
  --word-size N           word size do blastn-short (padrão: 7)
  --evalue   VALOR        e-value do BLAST (padrão: 1000)
  --min-pid  N            identidade mínima % para filtro (padrão: 70)
  --min-qcov N            cobertura mínima de query % para filtro (padrão: 70)
  --threads  N            threads (padrão: 4)
  -h, --help              mostra esta ajuda
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample)    SAMPLE="$2";       shift 2 ;;
    --input)     INPUT_FASTA="$2";  shift 2 ;;
    --db)        BLAST_DB_PATH="$2"; shift 2 ;;
    --word-size) WORD_SIZE="$2";    shift 2 ;;
    --evalue)    EVALUE="$2";       shift 2 ;;
    --min-pid)   MIN_PID="$2";      shift 2 ;;
    --min-qcov)  MIN_QCOV="$2";     shift 2 ;;
    --threads)   THREADS="$2";      shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "[ERRO] opção inválida: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ "$WORD_SIZE" != "7" || "$EVALUE" != "1000" ]]; then
  echo "[ERRO] perfis BLAST locais divergentes foram desativados; use o roteador canônico versionado." >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Validações
# ---------------------------------------------------------------------------
if [[ -z "$SAMPLE" ]]; then
  echo "[ERRO] --sample é obrigatório." >&2; exit 1
fi
if [[ -z "$INPUT_FASTA" ]]; then
  echo "[ERRO] --input é obrigatório." >&2; exit 1
fi
if [[ -z "$BLAST_DB_PATH" ]]; then
  echo "[ERRO] --db é obrigatório." >&2; exit 1
fi
SAMPLE="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE")"
if ! python3 -c 'import math,sys; values=[float(x) for x in sys.argv[1:3]]; threads=int(sys.argv[3]); sys.exit(0 if all(math.isfinite(x) and 0 <= x <= 100 for x in values) and threads > 0 else 1)' \
  "$MIN_PID" "$MIN_QCOV" "$THREADS"; then
  echo "[ERRO] --min-pid/--min-qcov devem estar em 0..100 e --threads deve ser positivo." >&2
  exit 2
fi

if [[ ! -f "$INPUT_FASTA" ]]; then
  echo "[AVISO] FASTA de fragmentos curtos não encontrado: $INPUT_FASTA"
  echo "        Etapa SHORT_FRAGMENT_BLAST ignorada."
  exit 0
fi

# Verifica se o FASTA tem alguma sequência
SEQ_COUNT=$(grep -c '^>' "$INPUT_FASTA" 2>/dev/null || true)
if [[ "${SEQ_COUNT:-0}" -eq 0 ]]; then
  echo "[AVISO] FASTA vazio (sem sequências): $INPUT_FASTA"
  echo "        Etapa SHORT_FRAGMENT_BLAST ignorada."
  exit 0
fi
python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fasta "$INPUT_FASTA" >/dev/null

# BLAST+'s own -db parser reads whitespace as a database-list separator, so
# a path containing spaces must be wrapped in embedded literal quotes to be
# kept as one database name (shell quoting alone does not affect this).
BLAST_DB_ARG="$BLAST_DB_PATH"
[[ "$BLAST_DB_PATH" == *[[:space:]]* ]] && BLAST_DB_ARG="\"${BLAST_DB_PATH}\""
if ! command -v blastdbcmd >/dev/null 2>&1 || ! blastdbcmd -db "$BLAST_DB_ARG" -info >/dev/null 2>&1; then
  echo "[ERRO] Banco BLAST inválido ou incompleto: ${BLAST_DB_PATH}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Diretório de saída
# ---------------------------------------------------------------------------
OUTDIR="${GENEIN_WORK_ROOT:-$REPO_ROOT}/results/blast"
mkdir -p "$OUTDIR"

BLAST_RAW="${OUTDIR}/${SAMPLE}_short_fragments_blast.tsv"
BLAST_FILTERED="${OUTDIR}/${SAMPLE}_short_fragments_filtered.tsv"
BLAST_FILTERED_PROVENANCE="${OUTDIR}/${SAMPLE}_short_fragments_filtered_provenance.json"

echo "[05] BLAST sensível para fragmentos curtos"
echo "     Amostra : $SAMPLE"
echo "     Input   : $INPUT_FASTA ($SEQ_COUNT sequências)"
echo "     DB      : $BLAST_DB_PATH"
echo "     Perfil  : roteamento canônico por comprimento (parâmetros registrados)"
echo "     Filtros : pident>=${MIN_PID}% qcov>=${MIN_QCOV}%"

# ---------------------------------------------------------------------------
# Executar BLAST (outfmt canônico 16 colunas via blast_router: ... qlen slen nident gaps)
# ---------------------------------------------------------------------------
python3 "$SCRIPTS_ROOT/evidence/blast_router.py" --query "$INPUT_FASTA" --db "$BLAST_DB_PATH" \
  --activation-policy "$EVIDENCE_ACTIVATION" --profiles "$EVIDENCE_PROFILES" --threads "$THREADS" --out-combined "$BLAST_RAW" \
  --provenance "${OUTDIR}/${SAMPLE}_short_fragments_blast_provenance.json"

RAW_HITS=$(wc -l < "$BLAST_RAW" 2>/dev/null || echo 0)
echo "     Hits brutos: $RAW_HITS"

# ---------------------------------------------------------------------------
# Filtrar por identidade e cobertura de query (pós-processamento; qcov derivado)
# Raw BLAST: 1..14 canônicos + 15=nident 16=gaps; qlen=$13 slen=$14 inalterados.
# ---------------------------------------------------------------------------

# Cabeçalho para o filtered TSV
BLAST_FILTERED_TMP="${BLAST_FILTERED}.tmp.$$"
trap 'rm -f "$BLAST_FILTERED_TMP"' EXIT
printf 'qseqid\tsseqid\tpident\tlength\tmismatch\tgapopen\tqstart\tqend\tsstart\tsend\tevalue\tbitscore\tqlen\tslen\tnident\tgaps\tqcov\n' \
  > "$BLAST_FILTERED_TMP"

awk -v min_pid="$MIN_PID" -v min_qcov="$MIN_QCOV" '
BEGIN { OFS="\t" }
{
  qseqid=$1; sseqid=$2; pident=$3; blast_length=$4; mismatch=$5; gapopen=$6
  qstart=$7; qend=$8; sstart=$9; send=$10; evalue=$11; bitscore=$12
  qlen=$13; slen=$14; nident=$15; gaps=$16

  # Calcular cobertura de query (proteção contra qlen=0)
  if (qlen > 0) {
    aln_len = (qend > qstart) ? (qend - qstart + 1) : (qstart - qend + 1)
    qcov = aln_len / qlen * 100.0
  } else {
    qcov = 0
  }

  if (pident >= min_pid && qcov >= min_qcov) {
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%.2f\n", \
      qseqid, sseqid, pident, blast_length, mismatch, gapopen, \
      qstart, qend, sstart, send, evalue, bitscore, qlen, slen, nident, gaps, qcov
  }
}
' "$BLAST_RAW" >> "$BLAST_FILTERED_TMP"
mv -f "$BLAST_FILTERED_TMP" "$BLAST_FILTERED"
trap - EXIT
python3 "$SCRIPTS_ROOT/evidence/write_provenance.py" \
  --config "$EVIDENCE_PROFILES" --out "$BLAST_FILTERED_PROVENANCE" \
  --artifact "query_fasta=$INPUT_FASTA" --artifact "blast_raw=$BLAST_RAW" \
  --artifact "blast_filtered=$BLAST_FILTERED" \
  --value "sample_id=$SAMPLE" --value "minimum_pident_percent=$MIN_PID" \
  --value "minimum_query_coverage_percent=$MIN_QCOV" \
  --value "blast_parameter_source=blast_routing_provenance"

FILTERED_HITS=$(( $(wc -l < "$BLAST_FILTERED") - 1 ))  # descontar cabeçalho
echo "     Hits filtrados (pident>=${MIN_PID}% qcov>=${MIN_QCOV}%): $FILTERED_HITS"
echo "     Resultado bruto   : $BLAST_RAW"
echo "     Resultado filtrado: $BLAST_FILTERED"
echo "     Proveniência      : $BLAST_FILTERED_PROVENANCE"

if [[ "$FILTERED_HITS" -eq 0 ]]; then
  echo "[AVISO] Nenhum hit passou os filtros de identidade e cobertura."
  echo "        Considere relaxar SHORT_FRAGMENT_MIN_PID ou SHORT_FRAGMENT_MIN_QCOV."
fi
