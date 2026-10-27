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
stop_install() {
  echo >&2
  echo "[ERRO] Instalação interrompida; ${1} Instale ${missing_system[*]} e rode de novo: bash bundle/install_wsl.sh" >&2
  echo "[ERROR] Installation stopped; ${2} Install ${missing_system[*]} and run again: bash bundle/install_wsl.sh" >&2
  exit 2
}
if ((${#missing_system[@]})); then
  echo "[AVISO] Pré-requisitos do sistema ausentes: ${missing_system[*]}" >&2
  echo "[WARN] Missing system prerequisites: ${missing_system[*]}" >&2
  echo "Instale: make python3 curl tar bzip2 ca-certificates coreutils findutils." >&2
  echo "Install: make python3 curl tar bzip2 ca-certificates coreutils findutils." >&2
  command -v apt-get >/dev/null 2>&1 || stop_install "não há apt-get neste sistema." "apt-get is not available on this system."
  apt_prefix=()
  if [[ "$EUID" -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || stop_install "sem sudo, peça a instalação ao administrador." "without sudo, ask an administrator to install them."
    apt_prefix=(sudo)
  fi
  # apt-get keeps its own output (including a sudo password prompt). A failure
  # still ends here, before any environment directory is created.
  if ! "${apt_prefix[@]}" apt-get update; then
    stop_install "o apt-get falhou." "apt-get failed."
  fi
  if ! "${apt_prefix[@]}" apt-get install -y make python3 curl tar bzip2 ca-certificates coreutils findutils; then
    stop_install "o apt-get falhou." "apt-get failed."
  fi
  for required in "${missing_system[@]}"; do
    need_cmd "$required" || stop_install "pré-requisito ainda ausente: ${required}." "prerequisite still missing: ${required}."
  done
fi
mkdir -p "$BIN_DIR" "$MAMBA_ROOT"

# Micromamba 2.9.0 (etiqueta 2.9.0-0). O hash é do tar.bz2 linux-64
# que contém bin/micromamba, não do binário ELF publicado à parte.
MICROMAMBA_VERSION="2.9.0"
MICROMAMBA_SHA256="8761c382127e6363bd9e0a2451aa3ef90d071a79133f736e2f759a3bf13040dd"
MICROMAMBA_URL="https://micro.mamba.pm/api/micromamba/linux-64/${MICROMAMBA_VERSION}"

verify_mamba_archive() {
  local file="$1"
  local got
  got="$(sha256sum "$file" | awk '{print $1}')"
  if [[ "$got" != "$MICROMAMBA_SHA256" ]]; then
    echo "[ERRO] Hash do micromamba ${MICROMAMBA_VERSION} não confere: $file" >&2
    echo "esperado ${MICROMAMBA_SHA256}" >&2
    echo "obtido   ${got}" >&2
    exit 2
  fi
}

# Instala micromamba (preferindo bundle/cache local em modo offline)
if [[ ! -x "$MICRO" ]]; then
  tmp="$(mktemp -d)"
  archive="$tmp/micromamba.tar.bz2"
  if local_bundle="$(resolve_local_mamba)"; then
    echo "[INFO] Usando micromamba local: $local_bundle"
    cp "$local_bundle" "$archive"
  else
    echo "[INFO] Bundle local não encontrado. Baixando micromamba ${MICROMAMBA_VERSION}..."
    curl --fail --location --silent --show-error --output "$archive" "$MICROMAMBA_URL"
  fi
  verify_mamba_archive "$archive"
  tar -xvjf "$archive" -C "$tmp" bin/micromamba
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
