#!/usr/bin/env bash
# Regressao do NO_GO do piloto DEV de 22/09/2026 (DEV_NEG_RANDOM).
#
# Montador que TERMINA normalmente (exit 0) com arquivo de contigs PRESENTE e
# VAZIO e uma tentativa concluida sem contigs: o wrapper deve sair 0 e publicar
# FASTA vazio, e o roteador deve registrar SOFT e sair 0 (a jusante,
# sample_steps.sh emite no_assembly). Saida ausente, FASTA invalido ou exit
# nao zero continuam falha tecnica (HARD). Executaveis controlados; nao e
# benchmark de montador.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
TMP_DIR="$(mktemp -d /tmp/genein-empty-assembly.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin"

python3 - "$TMP_DIR" <<'PY'
from pathlib import Path
import gzip
import sys

out = Path(sys.argv[1])
for mate in (1, 2):
    with gzip.open(out / f"R{mate}.fastq.gz", "wt", encoding="ascii") as handle:
        handle.write(f"@pair/{mate}\n{'ACGT' * 37}AC\n+\n{'I' * 150}\n")
PY

# spades.py falso: --meta usa FAKE_META_RESULT, senao FAKE_SPADES_RESULT.
#   crash   -> exit 21 sem saida (como "Invalid kmer coverage histogram")
#   empty   -> exit 0, contigs.fasta presente e vazio (metaSPAdes em DEV_NEG_RANDOM)
#   missing -> exit 0, sem contigs.fasta
#   garbage -> exit 0, contigs.fasta nao FASTA
#   long    -> exit 0, contig de 300 pb
cat >"$TMP_DIR/bin/spades.py" <<'FAKE_SPADES'
#!/usr/bin/env bash
set -euo pipefail
out=""; meta=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --meta) meta=1; shift ;;
    *) shift ;;
  esac
done
[[ -n "$out" ]] || exit 2
mode="${FAKE_SPADES_RESULT:-long}"
[[ $meta -eq 1 ]] && mode="${FAKE_META_RESULT:-long}"
case "$mode" in
  crash) echo "ERROR Invalid kmer coverage histogram" >&2; exit 21 ;;
  empty) mkdir -p "$out"; : > "$out/contigs.fasta" ;;
  missing) mkdir -p "$out" ;;
  garbage) mkdir -p "$out"; printf 'isto nao e FASTA\n' > "$out/contigs.fasta" ;;
  long) mkdir -p "$out"; printf '>long\n%s\n' "$(printf 'A%.0s' {1..300})" > "$out/contigs.fasta" ;;
esac
exit 0
FAKE_SPADES
cat >"$TMP_DIR/bin/velveth" <<'FAKE_VELVETH'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$1"
FAKE_VELVETH
cat >"$TMP_DIR/bin/velvetg" <<'FAKE_VELVETG'
#!/usr/bin/env bash
set -euo pipefail
out="$1"
case "${FAKE_VELVET_RESULT:-long}" in
  hard) exit 43 ;;
  empty) : > "$out/contigs.fa" ;;
  missing) : ;;
  long) printf '>long\n%s\n' "$(printf 'C%.0s' {1..300})" > "$out/contigs.fa" ;;
esac
exit 0
FAKE_VELVETG
chmod +x "$TMP_DIR/bin/spades.py" "$TMP_DIR/bin/velveth" "$TMP_DIR/bin/velvetg"

fail() { echo "FAIL: $*" >&2; exit 1; }

# run_router <assembler> <case_dir>; FAKE_* herdados do ambiente.
run_router() {
  local assembler="$1" case_dir="$2"
  set +e
  PATH="$TMP_DIR/bin:$PATH" PIPELINE_CONFIG_LOADED=1 FRAGMENT_HUNTER_KEEP_ALL_KMERS=false SAMPLE_NAME=NEGRAND SAMPLE_ID=NEGRAND \
    SAMPLE_R1="$TMP_DIR/R1.fastq.gz" SAMPLE_R2="$TMP_DIR/R2.fastq.gz" \
    ASSEMBLY_DIR="$TMP_DIR/$case_dir" GENEIN_WORK_ROOT="$TMP_DIR/$case_dir/work" \
    ASSEMBLER="$assembler" THREADS=1 \
    FAKE_SPADES_RESULT="${FAKE_SPADES_RESULT:-long}" FAKE_META_RESULT="${FAKE_META_RESULT:-long}" \
    FAKE_VELVET_RESULT="${FAKE_VELVET_RESULT:-long}" \
    bash scripts/pipeline/assembly_router.sh >"$TMP_DIR/$case_dir.router.log" 2>&1
  local rc=$?
  set -e
  return "$rc"
}
meta() { grep -qx "$2" "$TMP_DIR/$1/NEGRAND_assembly/assembly_metadata.env" || fail "$1: esperado $2"; }
canonical_empty() {
  local f="$TMP_DIR/$1/NEGRAND_assembly/contigs.fa"
  [[ -f "$f" && ! -s "$f" ]] || fail "$1: contigs.fa canonico deveria existir e estar vazio"
}

# 1. Replica exata de DEV_NEG_RANDOM: SPAdes aborta (21), metaSPAdes e Velvet
#    concluem sem contigs. Antes da correcao: exit 1 / HARD / recibo FAILED.
rc=0; FAKE_SPADES_RESULT=crash FAKE_META_RESULT=empty FAKE_VELVET_RESULT=empty run_router spades negrandom || rc=$?
[[ $rc -eq 0 ]] || fail "negrandom: roteador deveria sair 0 (saiu $rc)"
meta negrandom 'ASSEMBLY_FAILURE_TYPE="SOFT"'
meta negrandom 'ASSEMBLER_USED="metaspades"'
meta negrandom 'ASSEMBLY_FALLBACK=1'
meta negrandom 'ASSEMBLY_MAX_CONTIG_LEN=0'
canonical_empty negrandom

# 2. Saida velha nunca e atribuida a tentativa vazia atual.
mkdir -p "$TMP_DIR/stale/NEGRAND_metaspades" "$TMP_DIR/stale/NEGRAND_assembly"
printf '>old\n%s\n' "$(printf 'G%.0s' {1..300})" > "$TMP_DIR/stale/NEGRAND_metaspades/contigs.fasta"
printf '>old\n%s\n' "$(printf 'G%.0s' {1..300})" > "$TMP_DIR/stale/NEGRAND_assembly/contigs.fa"
rc=0; FAKE_SPADES_RESULT=crash FAKE_META_RESULT=empty FAKE_VELVET_RESULT=empty run_router spades stale || rc=$?
[[ $rc -eq 0 ]] || fail "stale: roteador deveria sair 0 (saiu $rc)"
canonical_empty stale
[[ ! -s "$TMP_DIR/stale/NEGRAND_metaspades/contigs.fasta" ]] || fail "stale: contigs velhos do metaSPAdes nao foram substituidos"
grep -q '^>old$' "$TMP_DIR/stale/NEGRAND_assembly/contigs.previous.fa" || fail "stale: contigs.previous.fa ausente"

# 3. Falha de ferramenta continua falha: saida ausente apos exit 0.
rc=0; FAKE_SPADES_RESULT=crash FAKE_META_RESULT=missing FAKE_VELVET_RESULT=missing run_router spades missing || rc=$?
[[ $rc -ne 0 ]] || fail "missing: saida ausente nao pode virar sucesso"
meta missing 'ASSEMBLY_FAILURE_TYPE="HARD"'

# 4. FASTA invalido e exit nao zero continuam HARD.
rc=0; FAKE_SPADES_RESULT=crash FAKE_META_RESULT=garbage FAKE_VELVET_RESULT=hard run_router spades garbage || rc=$?
[[ $rc -ne 0 ]] || fail "garbage: FASTA invalido nao pode virar sucesso"
meta garbage 'ASSEMBLY_FAILURE_TYPE="HARD"'
rc=0; FAKE_SPADES_RESULT=crash FAKE_META_RESULT=crash FAKE_VELVET_RESULT=hard run_router spades allcrash || rc=$?
[[ $rc -ne 0 ]] || fail "allcrash: todos os montadores abortaram e o roteador saiu 0"
meta allcrash 'ASSEMBLY_FAILURE_TYPE="HARD"'

# 5. Montador primario conclui vazio: SOFT sem fallback (SPAdes e Velvet).
rc=0; FAKE_SPADES_RESULT=empty run_router spades spadesempty || rc=$?
[[ $rc -eq 0 ]] || fail "spadesempty: saiu $rc"
meta spadesempty 'ASSEMBLY_FAILURE_TYPE="SOFT"'
meta spadesempty 'ASSEMBLER_USED="spades"'
meta spadesempty 'ASSEMBLY_FALLBACK=0'
canonical_empty spadesempty
rc=0; FAKE_VELVET_RESULT=empty run_router velvet velvetempty || rc=$?
[[ $rc -eq 0 ]] || fail "velvetempty: saiu $rc"
meta velvetempty 'ASSEMBLY_FAILURE_TYPE="SOFT"'
meta velvetempty 'ASSEMBLER_USED="velvet"'
canonical_empty velvetempty

# 6. Contrato direto dos wrappers.
wrap() {  # wrap <script> <case_dir> [args...]; retorna o exit code
  local script="$1" case_dir="$2"; shift 2
  set +e
  PATH="$TMP_DIR/bin:$PATH" PIPELINE_CONFIG_LOADED=1 FRAGMENT_HUNTER_KEEP_ALL_KMERS=false \
    R1="$TMP_DIR/R1.fastq.gz" R2="$TMP_DIR/R2.fastq.gz" ASSEMBLY_DIR="$TMP_DIR/$case_dir" \
    GENEIN_WORK_ROOT="$TMP_DIR/$case_dir/work" \
    FAKE_SPADES_RESULT="${FAKE_SPADES_RESULT:-long}" FAKE_META_RESULT="${FAKE_META_RESULT:-long}" \
    FAKE_VELVET_RESULT="${FAKE_VELVET_RESULT:-long}" \
    bash "scripts/pipeline/assemblers/$script" "$@" >/dev/null 2>&1
  local rc=$?
  set -e
  return "$rc"
}
rc=0; FAKE_META_RESULT=empty wrap metaspades.sh w_meta_empty NEGRAND 1 || rc=$?
[[ $rc -eq 0 ]] || fail "metaspades.sh vazio saiu $rc"
[[ -f "$TMP_DIR/w_meta_empty/NEGRAND_metaspades/contigs.fasta" && ! -s "$TMP_DIR/w_meta_empty/NEGRAND_metaspades/contigs.fasta" ]] \
  || fail "metaspades.sh nao publicou FASTA vazio"
rc=0; FAKE_META_RESULT=missing wrap metaspades.sh w_meta_missing NEGRAND 1 || rc=$?
[[ $rc -ne 0 ]] || fail "metaspades.sh sem saida deveria falhar"
rc=0; FAKE_SPADES_RESULT=empty wrap spades.sh w_spades_empty NEGRAND 1 || rc=$?
[[ $rc -eq 0 ]] || fail "spades.sh vazio saiu $rc"
rc=0; FAKE_SPADES_RESULT=missing wrap spades.sh w_spades_missing NEGRAND 1 || rc=$?
[[ $rc -ne 0 ]] || fail "spades.sh sem saida deveria falhar"
rc=0; FAKE_SPADES_RESULT=crash wrap spades.sh w_spades_crash NEGRAND 1 || rc=$?
[[ $rc -ne 0 ]] || fail "spades.sh com exit 21 deveria falhar"
rc=0; FAKE_VELVET_RESULT=empty wrap velvet.sh w_velvet_empty NEGRAND 31 || rc=$?
[[ $rc -eq 0 ]] || fail "velvet.sh vazio saiu $rc"
[[ -f "$TMP_DIR/w_velvet_empty/NEGRAND_velvet_k31/contigs.fa" && ! -s "$TMP_DIR/w_velvet_empty/NEGRAND_velvet_k31/contigs.fa" ]] \
  || fail "velvet.sh nao publicou FASTA vazio"
rc=0; FAKE_VELVET_RESULT=missing wrap velvet.sh w_velvet_missing NEGRAND 31 || rc=$?
[[ $rc -ne 0 ]] || fail "velvet.sh sem saida deveria falhar"

echo "PASS montagem concluida sem contigs -> SOFT/exit 0; ausente, invalida ou abortada -> HARD"
