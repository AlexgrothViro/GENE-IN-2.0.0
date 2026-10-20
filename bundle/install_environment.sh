#!/usr/bin/env bash
# Install the recorded Linux x86_64 environment and this source checkout.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MICRO="${1:?micromamba executable}"
ENV_DIR="${2:?environment prefix}"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo "[ERROR] This explicit lock supports Linux x86_64 only." >&2; exit 2;
}
if [[ ! -e "$ENV_DIR" ]]; then
  "$MICRO" create -y -p "$ENV_DIR" -f "$ROOT/environment.linux-64.explicit.txt"
fi
# Do not silently replace an existing scientific environment.
"$ENV_DIR/bin/python" "$ROOT/bundle/verify_environment.py" "$ENV_DIR" "$ROOT/environment.linux-64.explicit.txt"
pip_args=()
if [[ -n "${GENEIN_WHEELHOUSE:-}" ]]; then
  pip_args=(--no-index --find-links "$GENEIN_WHEELHOUSE")
fi
"$ENV_DIR/bin/python" -m pip install "${pip_args[@]}" --require-hashes --no-deps -r "$ROOT/requirements.lock.txt"
"$ENV_DIR/bin/python" -m pip install --no-build-isolation --no-deps -e "$ROOT"
"$ENV_DIR/bin/python" -m pip check
echo "[OK] Recorded dependencies and Gene-In installed in $ENV_DIR"
