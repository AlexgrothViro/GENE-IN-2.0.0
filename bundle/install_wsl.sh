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

# set -e would abort a bare apt-get before any product message. Record the
# status and stop here so a missing prerequisite never looks installed.
stop_install() {
  local status="$1"
  local pt="$2"
  local en="$3"
  echo "[ERRO] ${pt}" >&2
  echo "[ERROR] ${en}" >&2
  exit "$status"
}

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
  command -v apt-get >/dev/null 2>&1 || stop_install 2 \
    "Instale esses pacotes pelo gerenciador do sistema e execute novamente. O Gene-In não foi instalado." \
    "Install these packages with the system package manager and run again. Gene-In was not installed."
  apt_prefix=()
  if [[ "$EUID" -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || stop_install 2 \
      "Sem sudo: peça a instalação dos pré-requisitos ao administrador. O Gene-In não foi instalado." \
      "No sudo: ask an administrator to install the prerequisites. Gene-In was not installed."
    apt_prefix=(sudo)
  fi
  apt_status=0
  "${apt_prefix[@]}" apt-get update || apt_status=$?
  if (( apt_status != 0 )); then
    stop_install "$apt_status" \
      "Falha do apt-get update (código ${apt_status}). Ausentes: ${missing_system[*]}. O Gene-In não foi instalado." \
      "apt-get update failed (exit ${apt_status}). Missing: ${missing_system[*]}. Gene-In was not installed."
  fi
  apt_status=0
  "${apt_prefix[@]}" apt-get install -y make python3 curl tar bzip2 ca-certificates coreutils findutils || apt_status=$?
  if (( apt_status != 0 )); then
    stop_install "$apt_status" \
      "Falha do apt-get install (código ${apt_status}). Ausentes: ${missing_system[*]}. O Gene-In não foi instalado." \
      "apt-get install failed (exit ${apt_status}). Missing: ${missing_system[*]}. Gene-In was not installed."
  fi
  for required in "${missing_system[@]}"; do
    need_cmd "$required" || stop_install 2 \
      "Pré-requisito ainda ausente: ${required}. O Gene-In não foi instalado." \
      "Prerequisite still missing: ${required}. Gene-In was not installed."
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
