#!/usr/bin/env bash
# bundle/run.sh — Wrapper shell do Gene-In
# Chamado pelo launcher Windows (run.bat via WSL) ou diretamente no Linux.
# Usa ambiente micromamba isolado em ~/.gene-in-bundle/ para não
# depender do conda/mamba global do sistema.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$ROOT" == "/opt/genein" ]]; then
    BUNDLE_DIR="/opt/genein/bundle"
else
    BUNDLE_DIR="$HOME/.gene-in-bundle"
fi
BUNDLE_DIR="${GENEIN_BUNDLE_DIR:-$BUNDLE_DIR}"
BIN_DIR="$BUNDLE_DIR/bin"
MICRO="$BIN_DIR/micromamba"
ENV_DIR="$BUNDLE_DIR/env"
export GENEIN_ENV_DIR="$ENV_DIR"

# ─────────────────────────────────────────────────────────────────────
#  Garantir que micromamba usa o root isolado do Gene-In
#  (nunca usar base conda do sistema)
# ─────────────────────────────────────────────────────────────────────
export MAMBA_ROOT_PREFIX="$BUNDLE_DIR/mamba"
unset CONDA_PREFIX      2>/dev/null || true
unset CONDA_DEFAULT_ENV 2>/dev/null || true
unset CONDA_SHLVL       2>/dev/null || true

# ─────────────────────────────────────────────────────────────────────
#  Instalar se o ambiente não existir
# ─────────────────────────────────────────────────────────────────────
TARGET="${1:-help}"

case "$TARGET" in
    install|update-env)
        exec bash "$ROOT/bundle/install_wsl.sh"
        ;;
    uninstall-bundle)
        echo "[INFO] Removendo ambiente isolado Gene-In: $BUNDLE_DIR"
        if [[ "$ROOT" == "/opt/genein" ]]; then
            rm -rf "$ENV_DIR" "$MAMBA_ROOT_PREFIX" "$BIN_DIR"
        else
            rm -rf "$BUNDLE_DIR"
        fi
        echo "[OK] Ambiente isolado removido."
        exit 0
        ;;
esac

if [[ "$TARGET" != genein ]] && ! command -v make >/dev/null 2>&1; then
    echo "[ERRO] make não encontrado. Prepare os pré-requisitos com bash bundle/install_wsl.sh e repita o comando." >&2
    exit 2
fi

if [[ ! -x "$MICRO" || ! -d "$ENV_DIR" ]]; then
    echo "[INFO] Ambiente não instalado. Rodando installer..."
    bash "$ROOT/bundle/install_wsl.sh"
fi

shift || true

# ─────────────────────────────────────────────────────────────────────
#  Roda o alvo do Makefile dentro do ambiente isolado
# ─────────────────────────────────────────────────────────────────────
if [[ "$TARGET" == genein ]]; then
    cd "$ROOT"
    # An existing shared environment may still contain an editable installation
    # pointing at another checkout. Always run this bundle's source.
    export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
    exec "$MICRO" run -p "$ENV_DIR" python -m genein "$@"
fi
exec "$MICRO" run -p "$ENV_DIR" make -C "$ROOT" "$TARGET" "$@"
