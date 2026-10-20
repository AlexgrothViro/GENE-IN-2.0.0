#!/usr/bin/env bash
# uninstall_linux.sh — Desinstalador do Gene-In para Linux nativo
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "Erro: Este desinstalador precisa ser executado como root (sudo)." >&2
    exit 1
fi

ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes|--non-interactive)
            ASSUME_YES=1
            ;;
        -h|--help)
            echo "Uso: sudo ./uninstall_linux.sh [--yes|--non-interactive]"
            exit 0
            ;;
        *)
            echo "Erro: argumento invalido: $arg" >&2
            echo "Uso: sudo ./uninstall_linux.sh [--yes|--non-interactive]" >&2
            exit 2
            ;;
    esac
done

echo "====================================================================="
echo "  Gene-In — Desinstalador para Linux"
echo "====================================================================="
echo ""

if [[ "$ASSUME_YES" -ne 1 ]]; then
    read -r -p "Tem certeza que deseja desinstalar o Gene-In? [s/N]: " confirm
    if [[ ! "$confirm" =~ ^[Ss]$ ]]; then
        echo "Desinstalacao cancelada."
        exit 0
    fi
fi

echo "[INFO] Removendo diretorio de instalacao /opt/genein/..."
rm -rf /opt/genein

echo ""
echo "====================================================================="
echo "  [OK] Gene-In desinstalado com sucesso!"
echo "  Sua pasta de dados (em ~/genein-dados/) foi preservada."
echo "====================================================================="
echo ""
