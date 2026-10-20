#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo "[ERROR] Gene-In requires Linux x86_64 (Windows: WSL2 x86_64)." >&2
  exit 2
}
if [[ "$ROOT" == /opt/genein ]]; then
  BUNDLE_DIR="${GENEIN_BUNDLE_DIR:-$ROOT/bundle}"
else
  BUNDLE_DIR="${GENEIN_BUNDLE_DIR:-$HOME/.gene-in-bundle}"
fi
BIN_DIR="$BUNDLE_DIR/bin"
ENV_DIR="$BUNDLE_DIR/env"
MAMBA_ROOT="$BUNDLE_DIR/mamba"
MICRO="$BIN_DIR/micromamba"

export MAMBA_ROOT_PREFIX="$MAMBA_ROOT"

need_cmd() { command -v "$1" >/dev/null 2>&1; }

LOCAL_MAMBA_CANDIDATES=(
  "$ROOT/bundle/cache/micromamba.tar.bz2"
  "$ROOT/bundle/cache/micromamba-linux-64.tar.bz2"
  "$ROOT/bundle/micromamba.tar.bz2"
)

resolve_local_mamba() {
  local file
  for file in "${LOCAL_MAMBA_CANDIDATES[@]}"; do
    if [[ -f "$file" ]]; then
      echo "$file"
      return 0
    fi
  done
  return 1
}

echo "[INFO] Fonte: $ROOT"
missing_system=()
for required in make python3 curl tar bzip2 install find chmod; do
  need_cmd "$required" || missing_system+=("$required")
done
if ((${#missing_system[@]})); then
  echo "[AVISO] Pré-requisitos do sistema ausentes: ${missing_system[*]}" >&2
  echo "Instale: make python3 curl tar bzip2 ca-certificates coreutils findutils." >&2
  command -v apt-get >/dev/null 2>&1 || {
    echo "[ERRO] Instale esses pacotes pelo gerenciador do sistema e execute novamente." >&2; exit 2;
  }
  apt_prefix=()
  if [[ "$EUID" -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || {
      echo "[ERRO] Sem sudo: peça a instalação dos pré-requisitos ao administrador." >&2; exit 2;
    }
    apt_prefix=(sudo)
  fi
  "${apt_prefix[@]}" apt-get update
  "${apt_prefix[@]}" apt-get install -y make python3 curl tar bzip2 ca-certificates coreutils findutils
  for required in "${missing_system[@]}"; do
    need_cmd "$required" || { echo "[ERRO] Pré-requisito ainda ausente: $required" >&2; exit 2; }
  done
fi
mkdir -p "$BIN_DIR" "$MAMBA_ROOT"

# Instala micromamba (preferindo bundle/cache local em modo offline)
if [[ ! -x "$MICRO" ]]; then
  tmp="$(mktemp -d)"
  if local_bundle="$(resolve_local_mamba)"; then
    echo "[INFO] Usando micromamba local: $local_bundle"
    tar -xvjf "$local_bundle" -C "$tmp" bin/micromamba
  else
    echo "[INFO] Bundle local não encontrado. Baixando micromamba..."
    ( cd "$tmp" && curl --fail --location --silent --show-error https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba )
  fi
  install -m 0755 "$tmp/bin/micromamba" "$MICRO"
  rm -rf "$tmp"
else
  echo "[INFO] micromamba já existe: $MICRO"
fi

# Install exact recorded dependencies, preserving an incompatible existing env.
bash "$ROOT/bundle/install_environment.sh" "$MICRO" "$ENV_DIR"
# ZIP extraction does not consistently preserve executable bits on Linux.
find "$ROOT/scripts" -type f -name '*.sh' -exec chmod u+x {} +
echo "[OK] Use: bash bundle/run.sh genein --help"
