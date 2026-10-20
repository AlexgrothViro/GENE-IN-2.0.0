#!/usr/bin/env bash
set -euo pipefail
PATH="/usr/bin:/bin:${PATH:-}"

SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/out"

cat > "$TMP/bin/bowtie2" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
out=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-S" ]]; then out="$2"; shift 2; else shift; fi
done
printf '@HD\tVN:1.6\tSO:unknown\n' > "$out"
EOF

cat > "$TMP/bin/samtools" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cmd="$1"; shift
case "$cmd" in
  view) cat "${@: -1}" ;;
  sort)
    out=""; source=""
    while [[ $# -gt 0 ]]; do
      case "$1" in -o) out="$2"; shift 2 ;; -n) shift ;; *) source="$1"; shift ;; esac
    done
    if [[ -n "$source" && -f "$source" ]]; then cp "$source" "$out"; else cat > "$out"; fi
    ;;
  fixmate) cp "${@: -2:1}" "${@: -1}" ;;
  index) : > "${1}.bai" ;;
  *) exit 99 ;;
esac
EOF

cat > "$TMP/bin/python3" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
# The mapper checks this prerequisite before the controlled Python validator.
# Supply it explicitly so this regression does not require a system Bowtie2.
cp "$TMP/bin/python3" "$TMP/bin/bowtie2-inspect"
chmod +x "$TMP/bin/bowtie2" "$TMP/bin/bowtie2-inspect" "$TMP/bin/samtools" "$TMP/bin/python3"
printf '>ref\nACGT\n' > "$TMP/ref.fa"
printf '@r/1\nACGT\n+\nIIII\n' > "$TMP/r1.fastq"
printf '@r/2\nACGT\n+\nIIII\n' > "$TMP/r2.fastq"

set +e
PATH="$TMP/bin:/usr/bin:/bin" "$REPO_ROOT/scripts/evidence/map_read_support.sh" \
  --sample synthetic --index "$TMP/index" --reference "$TMP/ref.fa" \
  --r1 "$TMP/r1.fastq" --r2 "$TMP/r2.fastq" --out-dir "$TMP/out" \
  --library-mode shotgun --umi-mode tag --run-id synthetic-run >"$TMP/stdout.txt" 2>"$TMP/stderr.txt"
rc=$?
set -e

[[ "$rc" -ne 0 ]] || { echo "expected non-zero exit when umi_tools missing"; exit 1; }
grep -q 'FATAL' "$TMP/stderr.txt"
grep -q 'umi_tools' "$TMP/stderr.txt"
! grep -q 'UMI_DEDUP_UNAVAILABLE' "$TMP/stdout.txt" "$TMP/stderr.txt" "$TMP/out"/* 2>/dev/null || true
[[ ! -e "$TMP/out/read_support.tsv" ]] || ! grep -q 'UMI_DEDUP_UNAVAILABLE' "$TMP/out/read_support.tsv"
echo "[OK] ausência de UMI-tools com umi_mode!=none falha fechado (FATAL/non-zero)"
