#!/usr/bin/env bash
# install_wsl_dependencies.sh — Instalador assistido de dependencias minimas do Gene-In
# Chamado pelo launcher Windows (run.bat) quando make ou python3 estao ausentes.
# Nao deve ser chamado diretamente pelo pipeline cientifico.
set -euo pipefail

echo ""
echo "====================================================================="
echo "  Gene-In — Instalador de dependencias do sistema (WSL/Ubuntu)"
echo "====================================================================="
echo ""
echo "  Este script vai instalar os pacotes minimos necessarios para"
echo "  o Gene-In funcionar neste Ubuntu:"
echo ""
echo "    make  build-essential  git  curl  wget"
echo "    unzip  dos2unix  tar  bzip2  ca-certificates"
echo "    python3  python3-venv"
echo ""
echo "====================================================================="
echo ""

# ─────────────────────────────────────────────────────────────────────
#  Verificar se sudo existe
# ─────────────────────────────────────────────────────────────────────
if ! command -v sudo >/dev/null 2>&1; then
    echo "[ERRO] O comando 'sudo' nao foi encontrado neste Ubuntu."
    echo ""
    echo "  Se voce nao tiver permissao de administrador neste computador,"
    echo "  use uma conta com permissao de administrador para:"
    echo "    - Liberar permissao de sudo para seu usuario;"
    echo "    - Instalar os pacotes acima via conta de administrador."
    echo ""
    echo "  Comandos para instalar manualmente (como root ou com sudo liberado):"
    echo ""
    echo "    sudo apt update"
    echo "    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv"
    echo ""
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────
#  Atualizar lista de pacotes
# ─────────────────────────────────────────────────────────────────────
echo "[INFO] Atualizando lista de pacotes (sudo apt update)..."
echo "       (pode pedir sua senha do Ubuntu)"
echo ""

if ! sudo apt-get update; then
    echo ""
    echo "[ERRO] Falha ao atualizar a lista de pacotes."
    echo ""
    echo "  Possiveis causas:"
    echo "    - Sem conexao com a internet;"
    echo "    - Permissao de sudo negada;"
    echo "    - Politica de seguranca do computador bloqueou."
    echo ""
    echo "  Verifique se WSL, Ubuntu, sudo e acesso a internet nos"
    echo "  repositorios do Ubuntu estao liberados neste computador."
    echo ""
    echo "  Para tentar instalar manualmente, abra o Ubuntu e rode:"
    echo ""
    echo "    sudo apt update"
    echo "    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv"
    echo ""
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────
#  Instalar dependencias
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "[INFO] Instalando dependencias (sudo apt install)..."
echo ""

PKGS="make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv"

if ! sudo apt-get install -y $PKGS; then
    echo ""
    echo "[ERRO] Falha ao instalar os pacotes."
    echo ""
    echo "  Nao foi possivel instalar automaticamente as dependencias."
    echo ""
    echo "  Verifique se WSL, Ubuntu e sudo estao liberados,"
    echo "  ou rode os comandos abaixo manualmente:"
    echo ""
    echo "    sudo apt update"
    echo "    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv"
    echo ""
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────
#  Verificar resultado
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "[INFO] Verificando instalacao..."
echo ""

FALHOU=0

if command -v make >/dev/null 2>&1; then
    echo "  [OK] make:    $(command -v make)"
else
    echo "  [ERRO] make nao encontrado apos a instalacao."
    FALHOU=1
fi

if command -v python3 >/dev/null 2>&1; then
    echo "  [OK] python3: $(command -v python3)"
else
    echo "  [ERRO] python3 nao encontrado apos a instalacao."
    FALHOU=1
fi

echo ""

if [ "$FALHOU" -eq 0 ]; then
    echo "====================================================================="
    echo "  [OK] Dependencias instaladas com sucesso!"
    echo "  Feche esta janela e clique novamente em run.bat para abrir o Gene-In."
    echo "====================================================================="
    echo ""
    exit 0
else
    echo "====================================================================="
    echo "  [ERRO] Algumas dependencias nao foram encontradas apos a instalacao."
    echo "====================================================================="
    echo ""
    echo "  Tente instalar manualmente abrindo o Ubuntu e rodando:"
    echo ""
    echo "    sudo apt update"
    echo "    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv"
    echo ""
    echo "  Verifique se WSL, Ubuntu e sudo estao liberados neste computador."
    echo ""
    exit 1
fi
