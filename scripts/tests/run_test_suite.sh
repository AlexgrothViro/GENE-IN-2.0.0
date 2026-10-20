#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-engineering}"
# O repositório precisa estar no caminho junto com src/: os testes em
# scripts/tests importam `scripts.*` como namespace package (não existe
# scripts/__init__.py), e sem a raiz esses imports não resolvem.
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

# tests/test_cli.py exercita o ponto de entrada INSTALADO e um dos casos remove
# PYTHONPATH de propósito, então o pacote precisa estar instalado de fato — sem
# isso 13 testes falham com "No module named genein", o que parece defeito do
# programa e não é. A checagem ignora PYTHONPATH para não se autoiludir.
if ! env -u PYTHONPATH python3 -c \
  'from pathlib import Path; import genein, sys; assert Path(genein.__file__).resolve().parent == Path(sys.argv[1]).resolve() / "src/genein"' \
  "$ROOT_DIR" >/dev/null 2>&1; then
  printf '[SETUP] instalando o pacote em modo editável (necessário para tests/test_cli.py)\n'
  python3 -m pip install -e "$ROOT_DIR" --no-build-isolation --no-deps --quiet || {
    printf '[FATAL] não foi possível instalar esta fonte. Use um venv e rode: python3 -m pip install --no-build-isolation --no-deps -e .\n' >&2
    exit 1
  }
fi

if [[ -n "${GENEIN_TEST_ARTIFACT_ROOT:-}" ]]; then
  mkdir -p "$GENEIN_TEST_ARTIFACT_ROOT"
fi

step() {
  local label="$1"
  shift
  printf '\n[TEST:%s] %s\n' "$MODE" "$label"
  "$@"
}

require_commands() {
  local missing=()
  local command_name
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
  done
  if ((${#missing[@]})); then
    printf '[SKIP] ferramentas operacionais ausentes: %s\n' "${missing[*]}" >&2
    return 77
  fi
}

run_engineering() {
  echo "[SCOPE] Integridade, contratos, fixtures, concorrência e regressões."
  step "Python engenharia (sem módulos de otimização)" \
    python3 -m pytest -q -p no:cacheprovider scripts/tests --ignore=scripts/tests/test_validation_tracks.py
  step "API, CLI, lote e grafo (tests/, sem repetir scripts/tests)" \
    python3 -m pytest -q -p no:cacheprovider tests
  step "Roteamento/fallback de montagem com executáveis controlados" \
    bash scripts/tests/test_assembly_router_regressions.sh
  step "Montagem concluída sem contigs é SOFT; saída ausente/inválida é HARD" \
    bash scripts/tests/test_assembly_empty_output_regressions.sh
  step "Estado explícito sem UMI-tools no remapeamento controlado" \
    bash scripts/tests/evidence/test_map_read_support.sh

  mapfile -d '' shell_files < <(find . -type f -name '*.sh' -print0)
  echo "[TEST:$MODE] Sintaxe Bash de ${#shell_files[@]} scripts"
  for shell_file in "${shell_files[@]}"; do
    bash -n "$shell_file" || { echo "[FAIL] Bash syntax: $shell_file" >&2; return 1; }
  done
  step "Compilação Python" python3 -m compileall -q scripts
  if command -v node >/dev/null 2>&1; then
    step "Testes JavaScript do dashboard" node --test dashboard/tests/js_modules.test.mjs
  else
    echo "[SKIP] node ausente; módulos do dashboard não foram verificados nesta execução."
  fi
}

run_operational() {
  echo "[SCOPE] Ferramentas reais instaladas neste host."
  require_commands \
    python3 fastp bowtie2 bowtie2-build samtools \
    blastn blastdbcmd makeblastdb umi_tools \
    spades.py metaspades.py velveth velvetg || return $?
  step "fastp e filtro de hospedeiro com ferramentas reais" \
    python3 -m unittest scripts.tests.test_host_filter
  step "Evidence V2 com BLAST+ real e painel sintético" \
    bash scripts/tests/evidence/test_blast_e2e_real.sh
  step "Evidence V2 sidecars + Mapper v0.2.2 com BLAST+ real" \
    bash scripts/tests/evidence/test_mapper_blast_e2e_real.sh
  if git -C "$ROOT_DIR" rev-parse --verify HEAD >/dev/null 2>&1; then
    step "Mapeamento direto experimental com Bowtie2/Samtools reais" \
      bash scripts/tests/evidence/test_direct_map_e2e_real.sh
  else
    echo "[NÃO EXECUTADO] Mapeamento direto experimental exige proveniência Git; ZIP sem .git. Os testes canônicos continuam."
  fi
  step "Linhagem UMI (read_name, tag, none) com ferramentas reais" \
    bash scripts/tests/evidence/test_umi_lineage_e2e_real.sh "${GENEIN_TEST_ARTIFACT_ROOT:-${TMPDIR:-/tmp}}/umi-$(date +%s)-$$"
  step "Comparação de contigs com painel competitivo real" \
    bash scripts/tests/test_contig_comparison_e2e_real.sh
  step "Velvet, SPAdes e metaSPAdes reais" \
    bash scripts/tests/test_assembly_tools_smoke.sh
  step "Pipeline atual FASTQ→Evidence V2 (perfil default aberto) com ferramentas reais" \
    bash scripts/tests/test_pipeline_e2e_canonical.sh
  step "Saturação total pelo hospedeiro: desfecho reconhecido + recibo execution.json (Bowtie2 real)" \
    bash scripts/tests/test_host_saturation_e2e.sh
}

case "$MODE" in
  engineering)
    run_engineering
    ;;
  operational)
    run_operational
    ;;
  *)
    echo "Uso: $0 {engineering|operational}" >&2
    exit 2
    ;;
esac

printf '\n[PASS] suíte %s concluída dentro do escopo declarado.\n' "$MODE"
