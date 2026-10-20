#!/usr/bin/env bash
set -euo pipefail

SAMPLE=""; CONTIGS=""; BLAST=""; OUT=""; SEARCH_PROFILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample) SAMPLE="${2:-}"; shift 2 ;;
    --contigs) CONTIGS="${2:-}"; shift 2 ;;
    --blast) BLAST="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    --search-profile) SEARCH_PROFILE="${2:-}"; shift 2 ;;
    *) echo "[ERRO] arg inválido: $1" >&2; exit 1 ;;
  esac
done
[[ -z "$SAMPLE" || -z "$CONTIGS" || -z "$BLAST" || -z "$OUT" ]] && { echo "[ERRO] uso: --sample --contigs --blast --out" >&2; exit 1; }

METADATA_FILE="$(dirname "$CONTIGS")/assembly_metadata.env"
if [[ -f "$METADATA_FILE" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "$METADATA_FILE"
fi

mkdir -p "$(dirname "$OUT")"
OUT_TMP="${OUT}.tmp.$$"
trap 'rm -f "$OUT_TMP"' EXIT
contig_count=0
max_len=0
if [[ -s "$CONTIGS" ]]; then
  contig_count="$(grep -c '^>' "$CONTIGS" 2>/dev/null || echo 0)"
  max_len="$(awk '
    /^>/ { if (seqlen>max) max=seqlen; seqlen=0; next }
    { seqlen += length($0) }
    END { if (seqlen>max) max=seqlen; print (max+0) }
  ' "$CONTIGS" 2>/dev/null || echo 0)"
fi
hit_count=0
if [[ -s "$BLAST" ]]; then
  hit_count="$(wc -l < "$BLAST" 2>/dev/null || echo 0)"
fi

BLAST_OUTDIR="$(dirname "$OUT")/../blast"
mkdir -p "$BLAST_OUTDIR"
ADJ_TSV="${BLAST_OUTDIR}/${SAMPLE}_adj_identity.tsv"
python3 "$(dirname "$0")/adj_identity.py" --blast "$BLAST" --contigs "$CONTIGS" --out "$ADJ_TSV"
LABELED_TSV="${BLAST_OUTDIR}/${SAMPLE}_labeled_hits.tsv"
python3 "$(dirname "$0")/label_hits.py" "$ADJ_TSV" --out "$LABELED_TSV" > /dev/null
LEGACY_EVIDENCE_JSON="${BLAST_OUTDIR}/${SAMPLE}_legacy_evidence.json"
ADAPTATION_RUN_ID="${EVIDENCE_RUN_ID:-}"
if [[ -z "$ADAPTATION_RUN_ID" ]]; then
  ADAPTATION_RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
fi
ADAPTATION_ID="report-1.1-${SAMPLE}-${ADAPTATION_RUN_ID}"
python3 "$(dirname "$0")/../evidence/adapt_legacy_evidence.py" --sample "$SAMPLE" --labeled "$LABELED_TSV" \
  --run-id "legacy-${SAMPLE}-${ADAPTATION_RUN_ID}" --adaptation-id "$ADAPTATION_ID" --out "$LEGACY_EVIDENCE_JSON"
python3 "$(dirname "$0")/../evidence/export_evidence.py" --json "$LEGACY_EVIDENCE_JSON" \
  --compatibility-mode explicit_legacy_adaptation \
  --out "${BLAST_OUTDIR}/${SAMPLE}_legacy_evidence_report.md"
top_adj_summary=""
if [[ -s "$ADJ_TSV" ]]; then
  top_adj_summary="$(python3 "$(dirname "$0")/select_best_adjusted_hit.py" "$ADJ_TSV")"
fi

# ---------------------------------------------------------------------------
# Exportação FASTA dos contigs com hit viral
# ---------------------------------------------------------------------------
HIT_CONTIGS_FA="${BLAST_OUTDIR}/${SAMPLE}_hit_contigs.fa"
HIT_CONTIGS_SUMMARY="${BLAST_OUTDIR}/${SAMPLE}_hit_contigs_summary.tsv"

# Captura a saída do script para extrair as variáveis de estatística
# O script nunca retorna código != 0 em caso de "sem hits" — apenas cria arquivos vazios
export_output=""
export_output="$(python3 "$(dirname "$0")/export_hit_contigs.py" \
  --labeled  "$LABELED_TSV" \
  --contigs  "$CONTIGS" \
  --sample   "$SAMPLE" \
  --out-dir  "$BLAST_OUTDIR" \
  --classes  ALL \
  --min-len  0 2>/dev/null)" || true

# Parse das variáveis de estatística emitidas pelo script Python
_ec_count=0;   _ec_strong=0; _ec_moderate=0
_ec_strong=0;  _ec_strong_div=0; _ec_moderate=0
_ec_weak=0;    _ec_review=0;     _ec_refs=0
_ec_min=0;     _ec_median=0;     _ec_max=0; _ec_n50=0
_ec_missing=0
_ec_canonical=0

while IFS= read -r line; do
  case "$line" in
    EXPORT_HIT_CONTIGS_COUNT=*)            _ec_count="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_STRONG=*)           _ec_strong="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_STRONG_DIVERGENT=*) _ec_strong_div="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_MODERATE=*)         _ec_moderate="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_WEAK=*)             _ec_weak="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_REVIEW=*)           _ec_review="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_CANONICAL_CLAIM_COUNT=*) _ec_canonical="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_REFS=*)             _ec_refs="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_MIN=*)              _ec_min="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_MEDIAN=*)           _ec_median="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_MAX=*)              _ec_max="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_N50=*)              _ec_n50="${line#*=}" ;;
    EXPORT_HIT_CONTIGS_MISSING_IN_FASTA=*) _ec_missing="${line#*=}" ;;
  esac
done <<< "$export_output"

SELECTION_SUMMARY="${BLAST_OUTDIR}/${SAMPLE}_selection_summary.json"
_sel_assembly=0; _sel_sequences=0; _sel_qids=0; _sel_hsps=0; _sel_accessions=0
_sel_exported=0; _sel_pending=0; _sel_class=0; _sel_length=0; _sel_no_hit=0
if [[ -s "$SELECTION_SUMMARY" ]]; then
  mapfile -t _selection_values < <(python3 - "$SELECTION_SUMMARY" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
counts = data.get("counts_by_disposition", {})
for value in (
    data.get("assembly_contigs", 0), data.get("distinct_assembly_sequences", 0),
    data.get("blast_query_ids", 0), data.get("labeled_hit_rows", 0),
    data.get("distinct_hit_accessions", 0), counts.get("EXPORTED", 0),
    counts.get("PENDING_MISSING_CONTIG", 0), counts.get("EXCLUDED_CLASS_FILTER", 0),
    counts.get("EXCLUDED_LENGTH_FILTER", 0), counts.get("NO_BLAST_HIT", 0),
):
    print(int(value))
PY
  )
  _sel_assembly="${_selection_values[0]:-0}"; _sel_sequences="${_selection_values[1]:-0}"
  _sel_qids="${_selection_values[2]:-0}"; _sel_hsps="${_selection_values[3]:-0}"
  _sel_accessions="${_selection_values[4]:-0}"; _sel_exported="${_selection_values[5]:-0}"
  _sel_pending="${_selection_values[6]:-0}"; _sel_class="${_selection_values[7]:-0}"
  _sel_length="${_selection_values[8]:-0}"; _sel_no_hit="${_selection_values[9]:-0}"
fi

# ---------------------------------------------------------------------------
# Geração do relatório Markdown
# ---------------------------------------------------------------------------
# Perfil de busca (GEN-013): o relatório mínimo declara qual perfil rodou.
# O manifesto é opcional — sem ele o relatório sai exatamente como antes.
SEARCH_PROFILE_SECTION=""
if [[ -n "$SEARCH_PROFILE" && -s "$SEARCH_PROFILE" ]]; then
  SEARCH_PROFILE_SECTION="$(python3 - "$SEARCH_PROFILE" <<'PY' || true
import json, sys

# O relatório é UTF-8; não deixe o console do host escolher a codificação.
sys.stdout.reconfigure(encoding="utf-8")

try:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
except (OSError, ValueError):
    raise SystemExit(0)

profiles = manifest.get("profiles", {})
labels = {
    "A": "contigs vs banco direcionado (padrão público)",
    "B": "painel competitivo (perfil explícito)",
    "C": "fragmentos curtos + blastn-short no mesmo banco (perfil explícito)",
}
print("## Perfil de busca")
print()
print(f"- **Identidade:** `{manifest.get('identity', '')}`")
print(f"- **Perfis executados:** {manifest.get('selected', '')}")
requested = manifest.get("requested") or "nenhum (padrão público)"
print(f"- **Perfis pedidos no run:** {requested}")
print()
print("| Perfil | Ativo | Flags |")
print("|---|---|---|")
for key in ("A", "B", "C"):
    entry = profiles.get(key, {})
    active = "Sim" if entry.get("active") else "Não"
    print(f"| {key} — {labels[key]} | {active} | `{entry.get('flags', '')}` |")
print()
print(f"_Manifesto do perfil de busca: `{sys.argv[1]}`_")
PY
)"
fi

{
  echo "# Summary – $SAMPLE"
  echo
  if [[ -n "$SEARCH_PROFILE_SECTION" ]]; then
    echo "$SEARCH_PROFILE_SECTION"
    echo
  fi
  echo "## Assembly"
  echo "- Montador requisitado: ${ASSEMBLER_REQUESTED:-desconhecido}"
  echo "- Montador utilizado: ${ASSEMBLER_USED:-desconhecido}"
  echo "- Fallback ativado: $([[ ${ASSEMBLY_FALLBACK:-0} -eq 1 ]] && echo "Sim" || echo "Não")"
  echo "- Tipo de falha de montagem: ${ASSEMBLY_FAILURE_TYPE:-Nenhuma}"
  echo "- Contigs gerados: ${contig_count}"
  echo "- Maior contig (bp): ${max_len}"
  echo "- Resgate de leituras (Read-level) acionado: $([[ ${RESCUE_TRIGGERED:-0} -eq 1 ]] && echo "Sim" || echo "Não")"
  echo
  echo "## BLAST (vs banco viral selecionado)"
  echo "- HSPs/alinhamentos tabulares: ${hit_count} (um qseqid pode ter múltiplos HSPs e referências)"
  if [[ -n "$top_adj_summary" ]]; then
    echo "- Melhor identidade ajustada: ${top_adj_summary}"
  fi
  echo
  echo "### Top 5 hits (por adj_identity)"
  if [[ -s "$BLAST" ]]; then
    echo
    echo "|qseqid|sseqid|pident|length|qlen|aln_cov|adj_identity|evidence_class|risk_note|evalue|bitscore|"
    echo "|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|"
    # Replace | inside sseqid field with / to avoid breaking Markdown table columns
    mapfile -t _top5 < <(tail -n +2 "$LABELED_TSV" | sort -t$'\t' -k9,9gr)
    if [[ ${#_top5[@]} -gt 0 ]]; then
      printf '%s\n' "${_top5[@]:0:5}" | awk -F'\t' '{
        gsub(/\|/, "/", $2)
        printf "|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n",$1,$2,$3,$4,$7,$8,$9,$10,$11,$5,$6
      }'
    fi
  else
    echo "_Sem hits (arquivo BLAST vazio)_"
  fi
  echo

  echo "## Recuperação, exportação e avaliação posterior"
  echo
  echo "| Unidade/etapa | Contagem | Definição |"
  echo "|---|---:|---|"
  echo "| Contigs montados | ${_sel_assembly} | IDs FASTA |"
  echo "| Sequências distintas | ${_sel_sequences} | SHA-256 das sequências montadas |"
  echo "| Queries com hit BLAST | ${_sel_qids} | qseqids únicos no TSV classificado |"
  echo "| HSPs tabulados | ${_sel_hsps} | linhas do BLAST de origem |"
  echo "| Accessions atingidos | ${_sel_accessions} | sseqids únicos, sem soma como genomas |"
  echo "| Contigs exportados | ${_sel_exported} | após regra de melhor hit e filtros configurados |"
  echo "| Pendentes por sequência ausente | ${_sel_pending} | hit registrado, ID não localizado no FASTA de montagem |"
  echo "| Excluídos por classe | ${_sel_class} | regra CLASS-FILTER |"
  echo "| Excluídos por comprimento | ${_sel_length} | regra MIN-LENGTH-FILTER |"
  echo "| Contigs sem hit | ${_sel_no_hit} | mantidos no ledger como NO_BLAST_HIT |"
  echo
  echo "- **Regra de melhor hit:** classe, identidade ajustada, bitscore, cobertura da query e e-value, nessa ordem."
  echo "- **Filtros deste relatório:** classes ALL e comprimento mínimo 0 bp; nenhuma classe ou comprimento foi excluído. A classe REVIEW permanece registrada e não compõe a alegação canônica ACTIONABLE."
  echo "- **Seleção final para interpretação:** não executada por este relatório; exportação FASTA é retenção de candidatos, não seleção científica final."
  echo "- **Ledger completo:** \`${BLAST_OUTDIR}/${SAMPLE}_selection_ledger.tsv\`; resumo: \`${SELECTION_SUMMARY}\`. Loci não são calculados pelo relatório clássico; consulte a tabela Evidence V2 quando disponível."
  echo

  # -----------------------------------------------------------------------
  # Nova seção: Contigs com Hit Viral (FASTA exportado)
  # -----------------------------------------------------------------------
  echo "## Contigs com Hit Viral – Exportação FASTA"
  echo
  if [[ "${_ec_count}" -gt 0 ]] 2>/dev/null; then
    echo "- **Arquivo FASTA:** \`${HIT_CONTIGS_FA}\`"
    echo "- **Summary TSV:** \`${HIT_CONTIGS_SUMMARY}\`"
    echo "- **Total de contigs exportados:** ${_ec_count}"
    echo "- **Referências virais distintas atingidas:** ${_ec_refs}"
    echo
    echo "### Distribuição por legacy_label"
    echo
    echo "| Classe | Contigs |"
    echo "|---|---:|"
    [[ "${_ec_strong}"       -gt 0 ]] 2>/dev/null && echo "| STRONG           | ${_ec_strong}   |"
    [[ "${_ec_strong_div}"   -gt 0 ]] 2>/dev/null && echo "| STRONG_DIVERGENT | ${_ec_strong_div} |"
    [[ "${_ec_moderate}"     -gt 0 ]] 2>/dev/null && echo "| MODERATE         | ${_ec_moderate} |"
    [[ "${_ec_weak}"         -gt 0 ]] 2>/dev/null && echo "| WEAK_RECOVERABLE | ${_ec_weak}     |"
    [[ "${_ec_review}"       -gt 0 ]] 2>/dev/null && echo "| REVIEW           | ${_ec_review}   |"
    echo "- **Contigs ACTIONABLE na alegação canônica:** ${_ec_canonical}"
    if [[ "${_ec_review}" -gt 0 ]] 2>/dev/null; then
      echo
      echo "> **Nota:** hits REVIEW são sinal para auditoria/revisão -- não participam"
      echo "> da alegação canônica do pipeline. Apenas hits confidence_tier=ACTIONABLE"
      echo "> compõem essa alegação; um REVIEW secundário nunca substitui um hit"
      echo "> ACTIONABLE do mesmo contig. Veja a coluna confidence_tier em"
      echo "> \`${HIT_CONTIGS_SUMMARY}\`."
    fi
    echo
    echo "### Tamanho dos contigs exportados (bp)"
    echo
    echo "| Mínimo | Mediana | Máximo | N50 |"
    echo "|---:|---:|---:|---:|"
    echo "| ${_ec_min} | ${_ec_median} | ${_ec_max} | ${_ec_n50} |"
    if [[ "${_ec_missing}" -gt 0 ]] 2>/dev/null; then
      echo
      echo "> **Atenção:** ${_ec_missing} contig(s) presentes no labeled_hits.tsv não foram"
      echo "> localizados no contigs.fa e foram omitidos do FASTA. Verifique se o assembly"
      echo "> e o resultado BLAST correspondem à mesma execução."
    fi
    echo
    echo "> O arquivo FASTA contém os contigs candidatos e as métricas calculadas para o banco selecionado."
  else
    echo "_Nenhum contig com hit viral foi exportado para esta amostra._"
    echo "- **Contigs ACTIONABLE na alegação canônica:** 0"
    if [[ -f "$HIT_CONTIGS_FA" ]]; then
      echo
      echo "_(Arquivo FASTA vazio gerado em: \`${HIT_CONTIGS_FA}\`)_"
    fi
  fi
  RESCUE_TSV="${BLAST_OUTDIR}/${SAMPLE}_read_level_candidates.tsv"
  RESCUE_DECISIONS="${RESCUE_TSV}.decisions.tsv"
  RESCUE_PROVENANCE="${RESCUE_TSV}.provenance.json"
  RESCUE_RAW_TSV="${RESCUE_RAW_OUT:-}"
  if [[ -s "$RESCUE_RAW_TSV" || -s "$RESCUE_TSV" ]]; then
    n_reads=$(tail -n +2 "$RESCUE_TSV" | wc -l | tr -d ' ')
    raw_read_hsps=0
    [[ -z "$RESCUE_RAW_TSV" || ! -f "$RESCUE_RAW_TSV" ]] || raw_read_hsps=$(wc -l < "$RESCUE_RAW_TSV" | tr -d ' ')
    echo "## Resgate direto de reads (separado de contigs e loci)"
    echo
    echo "- Alinhamentos BLAST brutos: ${raw_read_hsps}"
    echo "- Templates/IDs selecionados após filtros: ${n_reads}"
    echo "- Critérios: identidade ≥90%; e-value ≤1e-5; alinhamento ≥80 bp ou ≥80% da query. Regra de desempate: maior bitscore por qseqid."
    echo "- Ledger de todos os alinhamentos aceitos/rejeitados: \`${RESCUE_DECISIONS}\`"
    echo "- Proveniência e contagens por decisão: \`${RESCUE_PROVENANCE}\`"
    if [[ -s "$RESCUE_PROVENANCE" ]]; then
      python3 - "$RESCUE_PROVENANCE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
for status, count in sorted(data.get("counts_by_disposition", {}).items()):
    print(f"- {status}: {count} alinhamento(s)")
PY
    fi
    echo
    if [[ $n_reads -gt 0 ]]; then
      echo "> [!NOTE]"
      echo "> Hits computacionais foram detectados por busca direta das reads; este resultado é separado da montagem e não confirma origem biológica."
      echo
      echo "- **Total de reads resgatadas:** ${n_reads}"
      echo "- **Arquivo de candidatos:** \`${RESCUE_TSV}\`"
      echo
      echo "### Top 5 reads candidatas resgatadas (ordenadas por bitscore)"
      echo
      echo "|qseqid|sseqid|pident|length|qlen|aln_cov|adj_identity|evidence_class|evalue|bitscore|"
      echo "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|"
      mapfile -t _rescue_top5 < <(tail -n +2 "$RESCUE_TSV" | sort -t$'\t' -k6,6nr)
      if [[ ${#_rescue_top5[@]} -gt 0 ]]; then
        printf '%s\n' "${_rescue_top5[@]:0:5}" | awk -F'\t' '{
          gsub(/\|/, "/", $2)
          printf "|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n",$1,$2,$3,$4,$7,$8,$9,$10,$5,$6
        }'
      fi
      echo
    fi
  fi

  echo "_Arquivos intermediários: \`${ADJ_TSV}\`, \`${LABELED_TSV}\`_"
} > "$OUT_TMP"
mv -f "$OUT_TMP" "$OUT"

echo "[OK] Relatório: $OUT"
echo "[OK] TSVs intermediários: $ADJ_TSV | $LABELED_TSV"
echo "[OK] FASTA de hits: $HIT_CONTIGS_FA (${_ec_count} contig(s))"
