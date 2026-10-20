#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

export HOST_ACCESSION="${HOST_ACCESSION:-GCF_000003025.6}"
export HOST_NAME="${HOST_NAME:-Sus scrofa}"
export HOST_INDEX_PREFIX="${HOST_INDEX_PREFIX:-${REPO_ROOT}/ref/host/sus_scrofa_bt2}"

exec "${SCRIPTS_ROOT}/ops/prepare_host_reference.sh" "$@"
