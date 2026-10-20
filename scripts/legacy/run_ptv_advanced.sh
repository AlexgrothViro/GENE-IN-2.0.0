#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

CONFIG_FILE="${REPO_ROOT}/config/picornavirus.env"
LEGACY_CONFIG="${REPO_ROOT}/config.env"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
elif [[ -f "${LEGACY_CONFIG}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${LEGACY_CONFIG}"
fi

source "${REPO_ROOT}/scripts/lib/common.sh"

if [[ $# -lt 1 ]]; then
  log_error "Uso: $0 SAMPLE [KMER]"
fi

SAMPLE="$1"
KMER="${2:-31}"

ROOT_DIR="${REPO_ROOT}"
RUN_SUFFIX="$(date +%Y%m%d_%H%M%S)"
WORK_DIR="${LEGACY_WORK_DIR:-${ROOT_DIR}/results/legacy/${SAMPLE}_k${KMER}_${RUN_SUFFIX}}"
BLAST_DB="${LEGACY_BLAST_DB:-${ROOT_DIR}/db/ptv_teschovirus}"
ASSEMBLY_DIR="${ROOT_DIR}/data/assemblies/${SAMPLE}_velvet_k${KMER}"

mkdir -p "$WORK_DIR"

python3 "${ROOT_DIR}/scripts/lib/input_validation.py" sample "$SAMPLE" >/dev/null
[[ -s "${ASSEMBLY_DIR}/contigs.fa" ]] || log_error "Assembly legada ausente: ${ASSEMBLY_DIR}/contigs.fa"
[[ -s "${BLAST_DB}.nin" || -s "${BLAST_DB}.ndb" ]] || log_error "Banco BLAST legado ausente ou incompleto: ${BLAST_DB}"
export LEGACY_WORK_DIR="$WORK_DIR"

export BLAST_DB

log_info "======================================="
log_info " Pipeline avançado PTV - SAMPLE=${SAMPLE} KMER=${KMER}"
log_info "======================================="

log_info "[1/7] make test (env, filtro hospedeiro, montagem, BLAST básico)..."
command -v blastn >/dev/null 2>&1 || log_error "blastn não encontrado no PATH"

log_info "[2/7] BLAST de confirmação com qseq/sseq..."
blastn \
  -query "${ASSEMBLY_DIR}/contigs.fa" \
  -db "${BLAST_DB}" \
  -out "${WORK_DIR}/ptv_hits.confirm.tsv" \
  -outfmt "6 qseqid sacc pident length mismatch gapopen evalue bitscore qstart qend sstart send qseq sseq" \
  -max_target_seqs 5 \
  -num_threads 4

log_info "[3/7] Identidade ajustada (adj_identity.py)..."
python3 "${ROOT_DIR}/scripts/pipeline/adj_identity.py" \
  "${WORK_DIR}/ptv_hits.confirm.tsv" \
  "${WORK_DIR}/ptv_hits.adjust.tsv"

log_info "[4/7] Relatório resumido (merge_report.py)..."
python3 "${SCRIPT_DIR}/merge_report.py"

log_info "[5/7] Plano de extensão de flancos (extend_plan.py)..."
python3 "${SCRIPT_DIR}/extend_plan.py"

log_info "[6/7] FASTA de flancos (emit_extend_fasta.py)..."
python3 "${SCRIPT_DIR}/emit_extend_fasta.py"

log_info "[7/7] Simulação de reads (sim_reads_clean.py) e rótulos (label_hits.py)..."
python3 "${SCRIPT_DIR}/sim_reads_clean.py"
python3 "${ROOT_DIR}/scripts/pipeline/label_hits.py" "${WORK_DIR}/ptv_hits.adjust.tsv" --out "${WORK_DIR}/ptv_hits.labels.tsv"

echo
log_info "Pipeline avançado concluído."
log_info "Arquivos principais em: ${WORK_DIR}"
echo "  - ptv_hits.confirm.tsv"
echo "  - ptv_hits.adjust.tsv"
echo "  - ptv_report.tsv"
echo "  - extend_plan.tsv"
echo "  - extend_regions.fasta"
echo "  - sim_R1.fastq.gz / sim_R2.fastq.gz"
echo "  - ptv_hits.labels.tsv"
