#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

source "${SCRIPTS_ROOT}/lib/common.sh"

SAMPLE=""
KMER="31"
MIN_PIDENT="85.0"
MIN_ALN_LEN="20"
METHOD="auto" # auto, iqtree
THREADS="4"

usage() {
  cat <<'USAGE'
Uso: scripts/experimental/advanced_analysis/run.sh [opções]

Opções:
  --sample NOME           Nome da amostra (obrigatório)
  --kmer K                K-mer para Velvet/SPAdes (padrão: 31)
  --min-pident PIDENT     Identidade mínima (%) para hits (padrão: 85.0)
  --min-aln-len LEN       Comprimento mínimo (pb) do alinhamento (padrão: 20)
  --method METODO         Método filogenético: auto ou iqtree (padrão: auto)
  --threads N             Número de threads (padrão: 4)
  -h, --help              Mostra esta ajuda
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample)
      SAMPLE="$2"
      shift 2
      ;;
    --kmer)
      KMER="$2"
      shift 2
      ;;
    --min-pident)
      MIN_PIDENT="$2"
      shift 2
      ;;
    --min-aln-len)
      MIN_ALN_LEN="$2"
      shift 2
      ;;
    --method)
      METHOD="$2"
      shift 2
      ;;
    --threads)
      THREADS="$2"
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

if [[ -z "$SAMPLE" ]]; then
  log_error "O parâmetro --sample é obrigatório."
fi

# Carregar arquivo de ambiente
# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

# Localizar o TSV do BLAST
TSV_PATH="${REPO_ROOT}/results/blast/${SAMPLE}_vs_db.tsv"
if [[ ! -f "$TSV_PATH" ]]; then
  TSV_PATH="${REPO_ROOT}/results/blast/${SAMPLE}_k${KMER}_vs_db.tsv"
fi

# Localizar o contigs.fa
CONTIGS_PATH="${REPO_ROOT}/data/assemblies/${SAMPLE}_assembly/contigs.fa"
if [[ ! -f "$CONTIGS_PATH" ]]; then
  CONTIGS_PATH="${REPO_ROOT}/data/assemblies/${SAMPLE}_velvet_k${KMER}/contigs.fa"
fi

if [[ ! -f "$TSV_PATH" ]]; then
  log_error "Arquivo TSV do BLAST não encontrado para amostra '$SAMPLE'. Execute o pipeline principal primeiro."
fi

if [[ ! -f "$CONTIGS_PATH" ]]; then
  log_error "Arquivo de contigs não encontrado para amostra '$SAMPLE'. Execute o pipeline principal primeiro."
fi

DB="${DB:-ptv}"
REF_FASTA="${REF_FASTA:-data/ref/${DB}.fa}"
if [[ ! -f "${REPO_ROOT}/${REF_FASTA}" ]]; then
  if [[ -f "${REPO_ROOT}/data/ref/ptv_db.fa" ]]; then
    REF_FASTA="data/ref/ptv_db.fa"
  else
    log_error "Referência FASTA não encontrada em '$REF_FASTA'."
  fi
fi

OUTDIR="${REPO_ROOT}/results/phylogeny/${SAMPLE}_k${KMER}"
mkdir -p "$OUTDIR"

log_info "Extraindo contigs correspondentes (identidade >= ${MIN_PIDENT}%, comprimento >= ${MIN_ALN_LEN} pb)..."
python3 "${SCRIPTS_ROOT}/pipeline/extract_hits.py" \
  --sample "$SAMPLE" \
  --kmer "$KMER" \
  --tsv "$TSV_PATH" \
  --contigs "$CONTIGS_PATH" \
  --ref "${REPO_ROOT}/${REF_FASTA}" \
  --min-pident "$MIN_PIDENT" \
  --min-aln-len "$MIN_ALN_LEN"

HITS_FA="${OUTDIR}/hits.fa"
REFS_FA="${OUTDIR}/refs.fa"
SUMMARY_TSV="${OUTDIR}/hits_summary.tsv"

REPORT_PATH="${REPO_ROOT}/results/reports/${SAMPLE}_advanced_evidence.md"
mkdir -p "$(dirname "$REPORT_PATH")"

if [[ ! -s "$HITS_FA" ]]; then
  log_warn "Nenhum contig atendeu aos critérios de filtragem (identidade >= ${MIN_PIDENT}%, comprimento >= ${MIN_ALN_LEN} pb)."
  cat <<EOF > "$REPORT_PATH"
# Relatório de Validação Filogenética Avançada - Amostra: ${SAMPLE}

**Data da Análise:** $(date '+%Y-%m-%d %H:%M:%S')
**Foco da Análise:** Recuperação e avaliação de contigs candidatos curtos e ultra-curtos.

## Parâmetros de Filtragem
*   **Identidade Mínima:** ${MIN_PIDENT}%
*   **Comprimento Mínimo:** ${MIN_ALN_LEN} pb
*   **K-mer:** ${KMER}

## Resultados da Filtragem
> [!WARNING]
> Nenhum contig atendeu aos critérios de filtragem informados.
>
> *   Total de contigs com hits extraídos: **0**
> *   Verifique se o comprimento mínimo (${MIN_ALN_LEN} pb) não está muito alto ou se o alinhamento com a referência possui cobertura suficiente.

### Próximos Passos Recomendados
1. Reduza o limiar de comprimento mínimo para 20 pb (se ainda não fez).
2. Verifique o arquivo original de alinhamento BLAST para conferir a identidade dos hits gerados.
EOF
  log_info "Relatório vazio gerado com sucesso em: $REPORT_PATH"
  exit 0
fi

log_info "Alinhando contigs com referências usando MAFFT..."

# Contar referências
NUM_REFS=$(grep -c "^>" "$REFS_FA" || true)

if [[ "$NUM_REFS" -eq 0 ]]; then
  cp "${REPO_ROOT}/${REF_FASTA}" "${OUTDIR}/refs_fixed.fa"
  REFS_FA="${OUTDIR}/refs_fixed.fa"
  NUM_REFS=$(grep -c "^>" "$REFS_FA" || true)
fi

ALN_OUT="${OUTDIR}/alignment.fa"

if [[ "$NUM_REFS" -gt 1 ]]; then
  log_info "Alinhando referências primeiro (${NUM_REFS} sequências)..."
  mafft --auto --thread "$THREADS" "$REFS_FA" > "${OUTDIR}/refs_aligned.fa" 2>/dev/null
  log_info "Adicionando contigs (hits.fa) ao alinhamento com --addfragments..."
  mafft --addfragments "$HITS_FA" --thread "$THREADS" "${OUTDIR}/refs_aligned.fa" > "$ALN_OUT" 2>/dev/null
else
  log_info "Apenas 1 referência encontrada. Alinhando diretamente a referência com contigs..."
  cat "$REFS_FA" "$HITS_FA" > "${OUTDIR}/combined.fa"
  mafft --auto --thread "$THREADS" "${OUTDIR}/combined.fa" > "$ALN_OUT" 2>/dev/null
fi

log_info "Alinhamento concluído com sucesso: $ALN_OUT"

TREE_OUT="${OUTDIR}/tree.nwk"
[[ "$METHOD" == "auto" || "$METHOD" == "iqtree" || "$METHOD" == "iqtree2" ]] || \
  log_error "Método '$METHOD' indisponível. FastTree não é aceito para posicionamento filogenético V2."

IQTREE_BIN=""
if command -v iqtree2 >/dev/null 2>&1; then
  IQTREE_BIN="$(command -v iqtree2)"
elif command -v iqtree >/dev/null 2>&1; then
  IQTREE_BIN="$(command -v iqtree)"
fi
IQTREE_AVAILABLE=false
[[ -z "$IQTREE_BIN" ]] || IQTREE_AVAILABLE=true

EVIDENCE_PROFILES="${EVIDENCE_PROFILES:-${REPO_ROOT}/config/evidence_profiles.json}"
EVIDENCE_ACTIVATION="${EVIDENCE_ACTIVATION:-${REPO_ROOT}/config/evidence_activation.json}"
PHYLOGENY_GATE="${OUTDIR}/phylogeny_gate.json"
GATE_ARGS=(--alignment "$ALN_OUT" --queries "$HITS_FA" --references "$REFS_FA" \
  --activation-policy "$EVIDENCE_ACTIVATION" --profiles "$EVIDENCE_PROFILES" --iqtree-available "$IQTREE_AVAILABLE" --out "$PHYLOGENY_GATE")
[[ -z "${PHYLOGENY_REFERENCE_METADATA:-}" ]] || GATE_ARGS+=(--reference-metadata "$PHYLOGENY_REFERENCE_METADATA")
COMPETITIVE_TSV="${EVIDENCE_COMPETITIVE_TSV:-}"
[[ -z "$COMPETITIVE_TSV" || ! -s "$COMPETITIVE_TSV" ]] || GATE_ARGS+=(--competitive "$COMPETITIVE_TSV")
if ! python3 "${SCRIPTS_ROOT}/evidence/phylogeny_gate.py" "${GATE_ARGS[@]}"; then
  log_warn "Posicionamento filogenético bloqueado pelos gates operacionais: ${PHYLOGENY_GATE}"
  cat <<EOF > "$REPORT_PATH"
# Posicionamento Filogenético Exploratório Bloqueado — ${SAMPLE}

Os critérios operacionais de comprimento, sítios informativos, qualidade, painel taxonômico ou disponibilidade do IQ-TREE não foram atendidos.

Consulte o arquivo de auditoria: \`${PHYLOGENY_GATE}\`.

Este bloqueio não altera a classificação oficial Gene-In 1.1.
EOF
  exit 0
fi

log_info "Executando posicionamento filogenético exploratório com IQ-TREE..."
IQTREE_VERSION="$($IQTREE_BIN --version 2>&1 | head -n 1)"
IQTREE_MAJOR="$(printf '%s' "$IQTREE_VERSION" | grep -oE '[0-9]+' | head -n 1 || true)"
IQTREE_MAJOR="${IQTREE_MAJOR:-1}"
(
  cd "$OUTDIR"
  if (( IQTREE_MAJOR >= 2 )); then
    "$IQTREE_BIN" -s "$(basename "$ALN_OUT")" -m MFP -B 1000 -T AUTO -pre tree_iq -quiet -redo
  else
    "$IQTREE_BIN" -s "$(basename "$ALN_OUT")" -m MFP -bb 1000 -nt AUTO -pre tree_iq -quiet -redo
  fi
  [[ -s tree_iq.treefile ]] || exit 1
  mv -f tree_iq.treefile tree.nwk
) || log_error "IQ-TREE falhou; nenhuma árvore alternativa foi gerada."
CHOSEN_METHOD="IQ-TREE ${IQTREE_MAJOR} / ModelFinder / UFBoot 1000"
log_info "Posicionamento filogenético exploratório gerado: $TREE_OUT"

cat <<EOF > "$REPORT_PATH"
# Relatório de Validação Filogenética Avançada - Amostra: ${SAMPLE}

**Data da Análise:** $(date '+%Y-%m-%d %H:%M:%S')
**Foco Principal:** Recuperação e avaliação filogenética exploratória de fragmentos curtos e ultra-curtos.

## Resumo dos Parâmetros Científicos
*   **Identidade Mínima:** ${MIN_PIDENT}%
*   **Comprimento Mínimo:** ${MIN_ALN_LEN} pb (adequado para fragmentos curtos de até 20 pb)
*   **Método Filogenético Utilizado:** ${CHOSEN_METHOD}
*   **Total de Contigs Validados:** **$(grep -c "^>" "$HITS_FA" || true)**

---

## Resultados do Alinhamento Múltiplo (MAFFT)
Os fragmentos curtos foram alinhados com segurança a um conjunto de genomas de referência usando **MAFFT** com a opção \`--addfragments\`. Esse método impede que sequências muito curtas degradem a qualidade do alinhamento global das referências.

### Estatísticas de Comprimento dos Contigs
$(python3 -c "
import os, sys
with open('$SUMMARY_TSV') as f:
    lines = [line.strip().split('\t') for line in f if line.strip()]
if len(lines) > 1:
    lens = [int(x[1]) for x in lines[1:]]
    import statistics
    print(f'*   **Comprimento Mínimo:** {min(lens)} pb')
    print(f'*   **Comprimento Médio:** {round(statistics.mean(lens), 1)} pb')
    print(f'*   **Comprimento Máximo:** {max(lens)} pb')
else:
    print('*   Nenhuma estatística disponível.')
")

---

## Detalhamento dos Hits
EOF

# Inserir tabela de hits
python3 -c "
import sys, csv
tsv_file = '$SUMMARY_TSV'
print('### Tabela de Contigs e Hits Encontrados')
print('| Contig | Comprimento (pb) | Referência Mais Próxima | Identidade (%) | Comprimento Alinhamento (pb) | E-value | Bitscore | Posição Ref |')
print('| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |')
with open(tsv_file) as f:
    r = csv.reader(f, delimiter='\t')
    header = next(r)
    for row in r:
        if len(row) < 9: continue
        contig, clen, ref, pident, alen, bit, evalue, sstart, send = row
        print(f'| \`{contig}\` | {clen} | \`{ref}\` | {pident}% | {alen} | {evalue} | {bit} | {sstart}..{send} |')
" >> "$REPORT_PATH"

cat <<EOF >> "$REPORT_PATH"

---

## Posicionamento Filogenético Exploratório
A árvore foi gerada usando **${CHOSEN_METHOD}** após aprovação dos gates operacionais. O resultado representa evidência computacional exploratória e não confirma identidade viral, infecção ou ausência de contaminação.

### Arquivos Gerados para Auditoria Acadêmica
*   **Alinhamento Múltiplo (FASTA):** \`${ALN_OUT}\`
*   **Árvore Filogenética (Newick):** \`${TREE_OUT}\`
*   **Tabela de Hits Simplificada (TSV):** \`${SUMMARY_TSV}\`

> [!NOTE]
> Para visualizar a árvore Newick filogenética de forma interativa, você pode carregar o arquivo \`${TREE_OUT}\` em plataformas como [iTOL (Interactive Tree Of Life)](https://itol.embl.de/) ou [Phylo.io](https://phylo.io/).

---
**Gene-In 1.0 - Módulo de Análise Filogenética Avançada**
EOF

log_info "Relatório gerado com sucesso em: $REPORT_PATH"
log_info "Análise Avançada concluída!"
