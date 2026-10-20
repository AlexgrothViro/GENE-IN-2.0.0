#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
LEGACY_CONFIG="${REPO_ROOT}/config.env"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

if [[ -f "${SCRIPTS_ROOT}/lib/common.sh" ]]; then
  source "${SCRIPTS_ROOT}/lib/common.sh"
fi

cd "${REPO_ROOT}"

if ! command -v dos2unix >/dev/null 2>&1; then
  echo "ERRO: dos2unix não encontrado. Rode scripts/ops/install_deps.sh ou instale-o manualmente." >&2
  exit 1
fi

echo "[INFO] Normalizando final de linha (LF) em arquivos rastreados..."
mapfile -t tracked_files < <(git ls-files '*.sh' '*.py' '*.md' '*.env' '*.tsv' '*.txt' 'Makefile')

# Inclui configs locais se existirem (mesmo que não estejam versionados)
if compgen -G 'config.env*' >/dev/null; then
  while IFS= read -r cfg; do
    tracked_files+=("$cfg")
  done < <(ls config.env*)
fi
if compgen -G 'config/picornavirus.env*' >/dev/null; then
  while IFS= read -r cfg; do
    tracked_files+=("$cfg")
  done < <(ls config/picornavirus.env*)
fi

if (( ${#tracked_files[@]} > 0 )); then
  dos2unix "${tracked_files[@]}"
else
  echo "[INFO] Nenhum arquivo correspondente encontrado."
fi

echo "[INFO] Ajustando permissões de execução em scripts/*.sh e scripts/*.py (ignora ausentes)..."
shopt -s nullglob
chmod +x scripts/*.sh scripts/*.py || true
shopt -u nullglob

echo "[INFO] Concluído. Confirme com 'git status' e reenvie os arquivos se necessário."
