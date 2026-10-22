#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Used by sourced genein_config_path.sh/common.sh for config and path resolution.
# shellcheck disable=SC2034
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

if [[ -f "${SCRIPTS_ROOT}/lib/common.sh" ]]; then
  source "${SCRIPTS_ROOT}/lib/common.sh"
fi

REQUIRED_PACKAGES=(
  build-essential     # fornece gcc/make para compilações auxiliares
  dos2unix            # normalização de finais de linha
  spades              # fornece spades.py
  velvet              # fornece velveth/velvetg
  ncbi-blast+         # fornece blastn/makeblastdb
  bowtie2             # fornece bowtie2/bowtie2-build
  samtools            # BAM, depth, coverage e deduplicacao posicional
  fastp               # controle de qualidade de leituras
  unzip               # extracao de pacotes NCBI Datasets
  mafft               # alinhador para filogenia
  fasttree            # construção de árvores rápidas
  ncbi-entrez-direct  # fornece esearch/efetch
  git                 # controle de versão / 00_fix_wsl.sh
  rsync               # sincronização de arquivos / build_bundle
  openssl             # criptografia / validação de licenças
  wget                # utilitário de download via CLI
  bzip2               # descompressão .tar.bz2 / micromamba
)

OPTIONAL_PACKAGES=(
)

APT_GET_BIN="$(command -v apt-get || true)"
if [[ -z "${APT_GET_BIN}" ]]; then
  echo "ERRO: apt-get não encontrado. Instalação automática indisponível neste ambiente." >&2
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "ERRO: precisa ser root ou ter sudo para instalar pacotes com apt-get." >&2
    exit 1
  fi
else
  SUDO=""
fi

on_error() {
  echo "ERRO: falha durante a instalação com apt-get. Verifique conectividade de rede, proxy e repositórios configurados." >&2
}
trap on_error ERR

install_packages() {
  local label="$1"; shift
  local packages=("$@")
  if (( ${#packages[@]} == 0 )); then
    return 0
  fi
  echo "[INFO] Instalando ${label}: ${packages[*]}"
  DEBIAN_FRONTEND=noninteractive ${SUDO} "${APT_GET_BIN}" update -y
  DEBIAN_FRONTEND=noninteractive ${SUDO} "${APT_GET_BIN}" install -y "${packages[@]}"
}

install_packages "dependências obrigatórias" "${REQUIRED_PACKAGES[@]}"

install_iqtree() {
  echo "[INFO] Instalando iqtree (fallback para iqtree2 se necessário)..."
  DEBIAN_FRONTEND=noninteractive ${SUDO} "${APT_GET_BIN}" update -y
  if DEBIAN_FRONTEND=noninteractive ${SUDO} "${APT_GET_BIN}" install -y iqtree; then
    return 0
  fi
  echo "[AVISO] pacote iqtree indisponível; tentando iqtree2..."
  if DEBIAN_FRONTEND=noninteractive ${SUDO} "${APT_GET_BIN}" install -y iqtree2; then
    return 0
  fi
  echo "ERRO: falha ao instalar iqtree ou iqtree2. Instale manualmente e reexecute scripts/ops/check_env.sh." >&2
  exit 1
}

install_iqtree

# Não falha se opcionais não existirem; são úteis para downloads.
set +e
install_packages "dependências opcionais" "${OPTIONAL_PACKAGES[@]}"
set -e

echo
echo "[INFO] Instalação concluída. Reexecute scripts/ops/check_env.sh para validar o ambiente."
