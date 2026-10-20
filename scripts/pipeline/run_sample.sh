#!/usr/bin/env bash
# Private execution boundary, shared with run.sh without batch dispatch.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/prepare_run.sh"
if [[ -n "$BATCH_MANIFEST" ]]; then
  echo "[FATAL] the internal sample runner does not accept batches" >&2
  exit 2
fi
source "$SCRIPT_DIR/sample_steps.sh"
