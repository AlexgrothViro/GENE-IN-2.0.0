#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"
OUT_ROOT="${REPO_ROOT}/ref/evidence_panels"; PANEL_ID=""; LEGACY_PREFIX=""; SOURCES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCES+=("$2"); shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --panel-id) PANEL_ID="$2"; shift 2 ;;
    --out-prefix) LEGACY_PREFIX="$2"; shift 2 ;;
    *) echo "[FATAL] invalid competitive DB option: $1" >&2; exit 2 ;;
  esac
done
if [[ -n "$LEGACY_PREFIX" ]]; then
  OUT_ROOT="$(dirname "$LEGACY_PREFIX")/panels"
  PANEL_ID="${PANEL_ID:-$(basename "$LEGACY_PREFIX")}-$(date -u +%Y%m%dT%H%M%SZ)"
fi
PANEL_ID="${PANEL_ID:-panel-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "$PANEL_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$ && ${#SOURCES[@]} -gt 0 ]] || {
  echo "[FATAL] valid --panel-id and at least one --source CATEGORY=FASTA are required" >&2; exit 2;
}
for cmd in makeblastdb bowtie2-build python3; do command -v "$cmd" >/dev/null 2>&1 || { echo "[FATAL] $cmd not found" >&2; exit 3; }; done
mkdir -p "$OUT_ROOT/.staging" "$OUT_ROOT/panels"
STAGING="$OUT_ROOT/.staging/$PANEL_ID"; FINAL="$OUT_ROOT/panels/$PANEL_ID"
[[ ! -e "$STAGING" && ! -e "$FINAL" ]] || { echo "[FATAL] panel id already exists: $PANEL_ID" >&2; exit 2; }
mkdir "$STAGING" || { echo "[FATAL] unable to reserve panel id atomically: $PANEL_ID" >&2; exit 2; }
mkdir -p "$STAGING/blast" "$STAGING/bowtie2"
ARGS=(); for source in "${SOURCES[@]}"; do ARGS+=(--source "$source"); done
python3 "$SCRIPT_DIR/build_competitive_panel.py" "${ARGS[@]}" --out-fasta "$STAGING/panel.fa" --out-labels "$STAGING/labels.tsv"
makeblastdb -in "$STAGING/panel.fa" -dbtype nucl -parse_seqids -out "$STAGING/blast/panel" > "$STAGING/makeblastdb.log"
bowtie2-build "$STAGING/panel.fa" "$STAGING/bowtie2/panel" > "$STAGING/bowtie2-build.log" 2>&1
FINAL_PATH="$(python3 "$SCRIPT_DIR/finalize_panel.py" --staging "$STAGING" --final "$FINAL" --panel-id "$PANEL_ID")"
echo "[OK] Competitive panel: $FINAL_PATH"
echo "[BLAST_DB] $FINAL_PATH/blast/panel"
echo "[BOWTIE2_INDEX] $FINAL_PATH/bowtie2/panel"
echo "[LABELS] $FINAL_PATH/labels.tsv"
