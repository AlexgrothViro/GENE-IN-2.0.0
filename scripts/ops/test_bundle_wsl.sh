#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-dev}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT"
bash scripts/ops/build_bundle_wsl.sh "$TAG"

TARBALL="$ROOT/dist/picornavirus-wsl-bundle-${TAG}.tar.gz"
[[ -s "$TARBALL" ]] || { echo "[ERRO] Tarball não encontrado: $TARBALL" >&2; exit 1; }

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

tar -xzf "$TARBALL" -C "$TMPDIR"
cd "$TMPDIR/picornavirus-wsl-bundle-$TAG"

bash bundle/run.sh smoke-test
echo "[OK] bundle smoke-test OK (TAG=$TAG)"
