#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/prepare_run.sh"
if [[ -n "$BATCH_MANIFEST" ]]; then
  exec python3 "$SCRIPT_DIR/run_batch.py" --batch-manifest "$BATCH_MANIFEST" --profiles "$EVIDENCE_PROFILES" \
    --evidence-root "$EVIDENCE_ROOT" --threads "${THREADS_OVERRIDE:-${THREADS:-4}}"
fi
source "$SCRIPT_DIR/sample_steps.sh"
