#!/usr/bin/env bash
# Preserve the public bundle name; use the verified source-only packager.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-$(date +%Y%m%d)}"
exec python3 "$ROOT/scripts/ops/build_release.py" \
  --output-dir "${GENEIN_RELEASE_OUTPUT:-$ROOT/dist}" \
  --name "picornavirus-wsl-bundle-${VERSION}"
