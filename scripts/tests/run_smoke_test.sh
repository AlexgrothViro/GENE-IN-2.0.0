#!/usr/bin/env bash
# ==============================================================================
# Gene-In — Script de Teste de Fumaça (Smoke Test) Genérico
# ==============================================================================
# Executa um teste de ponta a ponta usando dados sintéticos curtos gerados localmente.
# Garante a integridade dos scripts de montagem, roteamento e geração de relatórios.
# ==============================================================================

set -uo pipefail

# Configura o local para UTF-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT_DIR" || exit 1

# Cores para saída
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC_RESET='\033[0m'

log_smoke_pass() {
  echo -e "${GREEN}[SMOKE-PASS]${NC_RESET} $*"
}

log_smoke_fail() {
  echo -e "${RED}[SMOKE-FAIL]${NC_RESET} $*"
}

log_smoke_info() {
  echo -e "${YELLOW}[SMOKE-INFO]${NC_RESET} $*"
}

EXIT_STATUS=0
SAMPLE="SMOKE_DEMO"

log_smoke_info "=== INICIANDO TESTE DE FUMAÇA GENÉRICO (SMOKE TEST) ==="

# 1. Preparar diretórios
log_smoke_info "Preparando diretórios temporários de entrada..."
mkdir -p data/raw

if [[ ! -s "data/ref/ptv.fa" ]]; then
  log_smoke_info "Referencia PTV ausente; preparando data/ref/ptv.fa..."
  if ! bash scripts/legacy/ptv/fetch_fasta.sh data/ref/ptv.fa >/dev/null; then
    log_smoke_fail "Nao foi possivel preparar data/ref/ptv.fa."
    exit 1
  fi
fi

# 2. Gerar FASTQ sintético rápido de teste (50 reads pareadas para rodar muito rápido)
log_smoke_info "Gerando leituras de teste sintéticas..."
python3 scripts/ops/make_demo_fastq.py --ref data/ref/ptv.fa --outdir data/raw --sample "$SAMPLE" --pairs 50 --len 150 --insert 150 >/dev/null
if [[ $? -eq 0 && -f "data/raw/${SAMPLE}_R1.fastq.gz" ]]; then
  log_smoke_pass "Dados sintéticos gerados em data/raw/${SAMPLE}_R1.fastq.gz"
else
  log_smoke_fail "Erro ao gerar dados sintéticos de teste."
  exit 1
fi

# 3. Rodar pipeline principal em modo rápido
log_smoke_info "Executando pipeline de montagem e classificação no modo rápido..."
rm -rf "data/assemblies/${SAMPLE}_assembly"
bash scripts/pipeline/run.sh --sample "$SAMPLE" --assembler velvet --skip-qc --skip-host-filter
PIPELINE_RC=$?

if [[ $PIPELINE_RC -eq 0 ]]; then
  log_smoke_pass "Execução do pipeline finalizada com sucesso (exit code 0)."
else
  log_smoke_fail "Falha na execução do pipeline (exit code $PIPELINE_RC)."
  EXIT_STATUS=1
fi

# 4. Validar existência e formato dos metadados de montagem
METADATA_FILE="data/assemblies/${SAMPLE}_assembly/assembly_metadata.env"
if [[ -f "$METADATA_FILE" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "$METADATA_FILE"
  if [[ "${ASSEMBLER_USED:-}" == "velvet" && "${ASSEMBLY_FAILURE_TYPE:-}" == "NONE" ]]; then
    log_smoke_pass "Metadados de montagem gerados e válidos."
  else
    log_smoke_fail "Metadados de montagem incorretos: Assembler=${ASSEMBLER_USED:-}, Falha=${ASSEMBLY_FAILURE_TYPE:-}"
    EXIT_STATUS=1
  fi
else
  log_smoke_fail "Arquivo de metadados da montagem não encontrado: $METADATA_FILE"
  EXIT_STATUS=1
fi

# 5. Validar geração dos relatórios intermediários e finais
REPORT_FILE="results/reports/${SAMPLE}_summary.md"
LABELED_TSV="results/blast/${SAMPLE}_labeled_hits.tsv"
if [[ -f "$REPORT_FILE" && -f "$LABELED_TSV" ]]; then
  log_smoke_pass "Relatórios e TSVs de classificação estruturados com sucesso."
else
  log_smoke_fail "Arquivos de resultado ausentes (Relatório/TSV)."
  EXIT_STATUS=1
fi

# 6. Limpeza opcional dos dados temporários de teste
log_smoke_info "Limpando arquivos temporários do teste de fumaça..."
rm -f "data/raw/${SAMPLE}_R"*.fastq.gz
rm -rf "data/assemblies/${SAMPLE}_assembly"
rm -f "results/blast/${SAMPLE}"*
rm -f "results/reports/${SAMPLE}"*

echo "=============================================================================="
if [[ $EXIT_STATUS -eq 0 ]]; then
  echo -e "${GREEN}SMOKE TEST CONCLUÍDO COM SUCESSO! O pipeline está operacional.${NC_RESET}"
else
  echo -e "${RED}SMOKE TEST CONCLUÍDO COM ERROS. Verifique os componentes do pipeline.${NC_RESET}"
fi
echo "=============================================================================="

exit $EXIT_STATUS
