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
echo "[AVISO] O Builder não pode ser instalado sem acesso concedido ao repositório privado. A obtenção do código via Git começa agora; sem esse acesso, a instalação falha." >&2
CREATED_BUILDER_ENV=0
if [[ ! -d "$TARGET" ]]; then
  "$PYTHON" -m venv "$TARGET"
  CREATED_BUILDER_ENV=1
fi
remove_new_builder_env() {
  if [[ "$CREATED_BUILDER_ENV" -eq 1 ]]; then
    rm -rf "$TARGET"
    echo "[AVISO] O ambiente ${TARGET} criado nesta tentativa foi removido porque o pip falhou." >&2
  fi
}
SPEC="$("$PYTHON" "$ROOT/scripts/pipeline/assemblers/builder_adapter.py" install-spec)"
echo "[INFO] Instalando Builder 0.4.0 em ambiente separado."
# `if ! cmd` deixa $? em 0 quando o if é verdadeiro. O código do pip tem de ser
# gravado no próprio `||`, senão a falha sai como EXIT 0.
pip_status=0
"$TARGET/bin/python" -m pip install "$SPEC" || pip_status=$?
if [[ "$pip_status" -ne 0 ]]; then
  remove_new_builder_env
  exit "$pip_status"
fi
pip_status=0
"$TARGET/bin/python" -m pip check || pip_status=$?
if [[ "$pip_status" -ne 0 ]]; then
  remove_new_builder_env
  exit "$pip_status"
fi
GENEIN_BUILDER_BIN="$TARGET/bin/genein-builder" "$PYTHON" "$ROOT/scripts/pipeline/assemblers/builder_adapter.py" check
echo "[OK] Builder disponível na opção de montador do Gene-In."
