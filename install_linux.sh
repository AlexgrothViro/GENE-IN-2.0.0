#!/usr/bin/env bash
# install_linux.sh — Instalador do Gene-In para Linux nativo
set -euo pipefail

# 1. Exigir execucao como root/sudo
if [ "$EUID" -ne 0 ]; then
    echo "Erro: Este instalador precisa ser executado como root (sudo)." >&2
    exit 1
fi

# Conferir pré-requisitos antes de criar ou copiar a instalação.
for required_command in python3 rsync curl tar bzip2 install getent; do
    command -v "$required_command" >/dev/null 2>&1 || {
        echo "[ERRO] Comando necessário ausente: $required_command" >&2
        echo "Instale os pré-requisitos descritos em docs/installation-reproducibility.md." >&2
        exit 2
    }
done

# Detectar usuario real depois da conferência dos pré-requisitos.
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

# 2. Criar diretorio de instalacao e preparar log
INSTALL_DIR="/opt/genein"
mkdir -p "$INSTALL_DIR"
LOG_FILE="$INSTALL_DIR/install.log"

# Redirecionar stdout e stderr para o log e manter na tela
exec > >(tee -i "$LOG_FILE") 2>&1

echo "====================================================================="
echo "  Gene-In — Instalador para Linux Nativo"
echo "====================================================================="
echo "Data: $(date)"
echo "Usuario instalador: $REAL_USER"
echo "Diretorio de destino: $INSTALL_DIR"
echo "Log de instalacao: $LOG_FILE"
echo "====================================================================="
echo ""

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 3. Validar dependencias minimas (python3)
echo "[INFO] Validando dependencias minimas do sistema..."
if ! command -v python3 > /dev/null 2>&1; then
    echo "[ERRO] python3 nao encontrado no sistema."
    echo "       Por favor, instale o Python 3 antes de continuar."
    exit 1
fi
echo "  [OK] python3 encontrado."

# 4. Copiar arquivos para /opt/genein/
echo "[INFO] Copiando arquivos do software para $INSTALL_DIR..."
# Copia apenas os artefatos necessarios para execucao em producao.
# Isso evita levar arquivos de desenvolvimento, dados locais e launchers Windows.
rsync -a \
  --include '/Makefile' \
  --include '/README.md' \
  --include '/README.en.md' \
  --include '/LEIA_PRIMEIRO.md' \
  --include '/THIRD_PARTY_NOTICES.md' \
  --include '/RELEASE.json' \
  --include '/CHANGELOG.md' \
  --include '/LICENSE' \
  --include '/environment.yml' \
  --include '/environment.lock.yml' \
  --include '/environment.linux-64.explicit.txt' \
  --include '/requirements.lock.txt' \
  --include '/pyproject.toml' \
  --include '/VERSION' \
  --include '/src/***' \
  --include '/install_linux.sh' \
  --include '/run_linux.sh' \
  --include '/uninstall_linux.sh' \
  --include '/config.env.example' \
  --include '/install.log' \
  --include '/bundle/***' \
  --include '/config/***' \
  --include '/dashboard/***' \
  --include '/docs/***' \
  --include '/scripts/***' \
  --include '/ref/***' \
  --include '/genein.ico' \
  --include '/genein_dark.ico' \
  --exclude '*' \
  "$ROOT/" "$INSTALL_DIR/"

# 5. Criar diretorio de dados do usuario
USER_DATA_DIR="$REAL_HOME/genein-dados"
echo "[INFO] Configurando diretorio de dados do usuario em $USER_DATA_DIR..."
mkdir -p "$USER_DATA_DIR/data"
mkdir -p "$USER_DATA_DIR/results"
mkdir -p "$USER_DATA_DIR/logs"

# Garantir que a pasta de dados pertence ao usuario comum
chown -R "$REAL_USER:$REAL_USER" "$USER_DATA_DIR"

# 6. Criar links simbolicos sob /opt/genein/
echo "[INFO] Criando links simbolicos de dados..."
for name in data results logs; do
    target="$INSTALL_DIR/$name"
    if [[ -L "$target" && "$(readlink "$target")" == "$USER_DATA_DIR/$name" ]]; then
        continue
    fi
    if [[ -e "$target" || -L "$target" ]]; then
        echo "[ERROR] Existing $target preserved. Move it explicitly before installing." >&2
        exit 2
    fi
    ln -s "$USER_DATA_DIR/$name" "$target"
done

# 7. Configurar micromamba e ambiente isolado
BUNDLE_DIR="$INSTALL_DIR/bundle"
BIN_DIR="$BUNDLE_DIR/bin"
ENV_DIR="$BUNDLE_DIR/env"
MAMBA_ROOT="$BUNDLE_DIR/mamba"
MICRO="$BIN_DIR/micromamba"

echo "[INFO] Configurando ambiente virtual micromamba em $BUNDLE_DIR..."
mkdir -p "$BIN_DIR" "$MAMBA_ROOT"

LOCAL_MAMBA="$INSTALL_DIR/bundle/cache/micromamba.tar.bz2"
if [[ -f "$LOCAL_MAMBA" ]]; then
    echo "  [INFO] Instalando micromamba a partir de cache local..."
    tmp="$(mktemp -d)"
    tar -xjf "$LOCAL_MAMBA" -C "$tmp" bin/micromamba
    install -m 0755 "$tmp/bin/micromamba" "$MICRO"
    rm -rf "$tmp"
else
    echo "  [INFO] Baixando micromamba..."
    tmp="$(mktemp -d)"
    curl --fail --location --silent --show-error https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$tmp" bin/micromamba
    install -m 0755 "$tmp/bin/micromamba" "$MICRO"
    rm -rf "$tmp"
fi

export MAMBA_ROOT_PREFIX="$MAMBA_ROOT"
unset CONDA_PREFIX 2>/dev/null || true
unset CONDA_DEFAULT_ENV 2>/dev/null || true
unset CONDA_SHLVL 2>/dev/null || true

echo "[INFO] Criando/atualizando ambiente bioconda a partir de environment.yml..."
bash "$INSTALL_DIR/bundle/install_environment.sh" "$MICRO" "$ENV_DIR"

# 8. Configurar script de desinstalacao e permissoes
echo "[INFO] Configurando script de desinstalacao..."
cp "$INSTALL_DIR/uninstall_linux.sh" "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/uninstall.sh"
rm -f "$INSTALL_DIR/uninstall_linux.sh"

# Ajustar permissoes de execucao
chmod +x "$INSTALL_DIR/run_linux.sh"
chmod +x "$INSTALL_DIR/scripts"/*.sh 2>/dev/null || true
chmod +x "$INSTALL_DIR/scripts"/*.py 2>/dev/null || true

# Configurar propriedade da instalacao para o usuario real.
# O Gene-In possui configuracoes locais editaveis (ex.: config/picornavirus.env).
chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"
chmod -R u+rwX,go+rX "$INSTALL_DIR"

echo ""
echo "====================================================================="
echo "  [OK] Instalacao do Gene-In concluida com sucesso!"
echo "====================================================================="
echo ""
echo "  Para iniciar o painel do Gene-In, execute:"
echo "    $INSTALL_DIR/run_linux.sh"
echo ""
echo "  Acesse o dashboard em: http://localhost:8000"
echo "  Sua pasta de dados locais esta em: $USER_DATA_DIR"
echo "====================================================================="
echo ""
