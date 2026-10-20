#!/usr/bin/env bash
# Compatibility entrypoint. Python owns batch iteration and child processes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/../pipeline/run_batch.py" "$@"
