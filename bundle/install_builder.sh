#!/usr/bin/env bash
# Dependência opcional em ambiente próprio; não modifica o ambiente científico.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="${GENEIN_BUNDLE_DIR:-$HOME/.gene-in-bundle}"
PYTHON="$BUNDLE_DIR/env/bin/python"
TARGET="$BUNDLE_DIR/builder-env"
if [[ ! -x "$PYTHON" ]]; then
  echo "[ERRO] Instale primeiro o Gene-In: bash bundle/install_wsl.sh" >&2
  exit 2
fi
if ! command -v git >/dev/null 2>&1; then
  echo "[ERRO] Git é necessário para obter o Builder." >&2
  exit 2
fi
if [[ -e "$TARGET" && ! -x "$TARGET/bin/python" ]]; then
  echo "[ERRO] $TARGET existe, mas não é um ambiente utilizável. Preserve-o e escolha outro GENEIN_BUNDLE_DIR." >&2
  exit 2
fi
if [[ ! -d "$TARGET" ]]; then
  "$PYTHON" -m venv "$TARGET"
fi
SPEC="$("$PYTHON" "$ROOT/scripts/pipeline/assemblers/builder_adapter.py" install-spec)"
echo "[INFO] Instalando Builder 0.4.0 em ambiente separado. É necessário acesso ao repositório privado."
"$TARGET/bin/python" -m pip install "$SPEC"
"$TARGET/bin/python" -m pip check
GENEIN_BUILDER_BIN="$TARGET/bin/genein-builder" "$PYTHON" "$ROOT/scripts/pipeline/assemblers/builder_adapter.py" check
echo "[OK] Builder disponível na opção de montador do Gene-In."
