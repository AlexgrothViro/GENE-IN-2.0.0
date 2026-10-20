#!/usr/bin/env bash
set -euo pipefail
export GENE_IN_ENV_BIN="${GENE_IN_ENV_BIN:-${GENEIN_BUNDLE_DIR:-$HOME/.gene-in-bundle}/env/bin}"
export PATH="$GENE_IN_ENV_BIN:$PATH"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/etapa3/gi-eg002-mapper-v0.2.2/verification"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
UMI_LOG="$ROOT/logs/etapa3/gi-eg002-mapper-v0.2.2/umi-e2e/$RUN_STAMP"
mkdir -p "$LOG"
{
echo "=== VERSIONS ==="
python3 -V
blastn -version
bowtie2 --version | sed -n '1p'
samtools --version | sed -n '1,2p'
umi_tools --version
python3 -c 'import importlib.metadata,pytest,sys; print("python", sys.version.split()[0]); print("jsonschema", importlib.metadata.version("jsonschema")); print("pytest", pytest.__version__); print("executable", sys.executable)'

echo "=== UNITTEST EVIDENCE ==="
python3 -m unittest discover -s scripts/tests/evidence -q
echo "unittest_exit=0"
python3 -m unittest scripts.tests.test_contig_comparison -q
echo "contig_exit=0"

echo "=== PYTEST EVIDENCE_GRAPH ==="
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
(python3 -m pytest -q tests --basetemp="$ROOT/logs/etapa3/gi-eg002-mapper-v0.2.2/pytest-basetemp")
echo "pytest_exit=0"

echo "=== SHELL CHECKS ==="
bash -n scripts/legacy/ptv/blast.sh scripts/pipeline/blast_short_fragments.sh scripts/pipeline/run.sh \
  scripts/evidence/run.sh scripts/evidence/map_read_support.sh \
  scripts/tests/evidence/test_map_read_support.sh \
  scripts/tests/evidence/test_mapper_blast_e2e_real.sh \
  scripts/tests/evidence/test_umi_lineage_e2e_real.sh
echo "bash_n_ok"
shellcheck -x -P "$ROOT/scripts" scripts/evidence/run.sh scripts/evidence/map_read_support.sh \
  scripts/tests/evidence/test_mapper_blast_e2e_real.sh \
  scripts/tests/evidence/test_umi_lineage_e2e_real.sh
echo "shellcheck_ok"
bash scripts/tests/evidence/test_map_read_support.sh
echo "map_read_support_ok"

echo "=== E2E BLAST MAPPER ==="
bash scripts/tests/evidence/test_mapper_blast_e2e_real.sh
echo "blast_mapper_e2e_ok"

echo "=== E2E UMI ==="
bash scripts/tests/evidence/test_umi_lineage_e2e_real.sh "$UMI_LOG"
echo "umi_e2e_ok"

echo "=== GIT DIFF CHECK ==="
git -c core.autocrlf=true diff --check
echo "git_diff_check_ok"
echo "=== DONE ==="
echo "LOG_DIR=$LOG"
echo "UMI_LOG_DIR=$UMI_LOG"
} 2>&1 | tee "$LOG/verification.log"
