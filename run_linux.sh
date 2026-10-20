#!/usr/bin/env bash
# Launcher Linux nativo. A execução usa o mesmo wrapper isolado do WSL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$(uname -s)" == "Linux" ]] || {
  echo "[ERRO] Use este launcher somente no Linux." >&2
  exit 1
}

if [[ $# -eq 0 ]]; then
  set -- ux
fi

exec bash "$ROOT/bundle/run.sh" "$@"
