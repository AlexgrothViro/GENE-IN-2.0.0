#!/usr/bin/env bash
# Braço builder no roteador, com o executável 0.4.0 simulado e a fixture pipeline_e2e.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
TMP_DIR="$(mktemp -d /tmp/genein-builder-arm.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/work"
PIN="af7cb088b3013df07fd3abfaa23ba89dba42cf6b"
INSTALLED="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

python3 - "$TMP_DIR" "$ROOT_DIR/scripts/tests/fixtures/pipeline_e2e/target.fa" <<'PY'
import gzip
import sys
from pathlib import Path

out = Path(sys.argv[1])
sequence = []
for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
    if line.startswith(">"):
        continue
    sequence.append(line.strip())
genome = "".join(sequence)
read = genome[:80]
if len(read) < 80:
    raise SystemExit("fixture curta demais")
for mate in (1, 2):
    with gzip.open(out / f"R{mate}.fastq.gz", "wt", encoding="ascii") as handle:
        handle.write(f"@fixture/{mate}\n{read}\n+\n{'I' * len(read)}\n")
PY

cat >"$TMP_DIR/bin/genein-builder" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then
  printf 'genein-builder 0.4.0\n'
  exit 0
fi
printf '%s\n' "$@" > "${MOCK_BUILDER_ARGS:?}"
[[ "${1:-}" == "run" ]] || exit 2
shift
for arg in "$@"; do
  if [[ "$arg" == "--threads" || "$arg" == "--single" ]]; then
    echo "flag rejeitada: $arg" >&2
    exit 2
  fi
done
r1=""
saida=""
motor="v1"
threads=""
hospedeiro=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --r1) r1="${2:-}"; shift 2 ;;
    --r2) shift 2 ;;
    --saida) saida="${2:-}"; shift 2 ;;
    --motor) motor="${2:-}"; shift 2 ;;
    -t) threads="${2:-}"; shift 2 ;;
    --hospedeiro) hospedeiro="${2:-}"; shift 2 ;;
    --fragmentos) shift ;;
    *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$r1" && -n "$saida" && -z "$hospedeiro" ]] || exit 2
if [[ -n "$threads" && "$motor" != "megahit" ]]; then
  echo "-t só vale com --motor megahit" >&2
  exit 2
fi
mkdir -p "$saida"
manifest() {
  printf '{"genein_builder": "0.4.0", "status": "%s", "commit": "%s"}\n' \
    "$1" "${MOCK_BUILDER_COMMIT:?}" > "$saida/manifesto_execucao.json"
}
head="fragmento	comprimento	n_kmers	cobertura_mediana	cobertura_media	phred_medio	phred_mediana"
restricted() {
  printf '%s\n' "$head	restricao	faixa" "$@" > "$saida/fragmentos/fragmentos_restritos.tsv"
}
case "${MOCK_BUILDER_MODE:-ok}" in
  ok)
    mkdir -p "$saida/fragmentos"
    # o contig de 240 pb sai em contigs.fasta e de novo em fragmentos/ (0.4.0)
    for destino in "$saida/contigs.fasta" "$saida/fragmentos/fragmentos.fasta"; do
      {
        echo ">NODE_1 len=240"
        printf 'A%.0s' {1..240} | fold -w 80
        echo
      } > "$destino"
    done
    printf '%s\n' "# fragmentos >= 50 pb" "$head	faixa" "NODE_1	240	210	6	6	35	35	>=200" \
      > "$saida/fragmentos/fragmentos.tsv"
    restricted "f36	36	6	2	2	30	30	ESPECIFICIDADE_NAO_VALIDADA	31-49" \
      "f12	12	0					ESPECIFICIDADE_NAO_VALIDADA	<31"
    {
      echo ">f36 len=36"
      printf 'C%.0s' {1..36}
      echo
      echo ">f12 len=12"
      printf 'G%.0s' {1..12}
      echo
    } > "$saida/fragmentos/fragmentos_restritos.fasta"
    manifest ok
    ;;
  fragments)
    mkdir -p "$saida/fragmentos"
    : > "$saida/contigs.fasta"
    printf '%s\n' "# comentario" "$head	faixa" > "$saida/fragmentos/fragmentos.tsv"
    : > "$saida/fragmentos/fragmentos.fasta"
    restricted "f36	36	6	2	2	30	30	ESPECIFICIDADE_NAO_VALIDADA	31-49"
    {
      echo ">f36 len=36"
      printf 'C%.0s' {1..36}
      echo
    } > "$saida/fragmentos/fragmentos_restritos.fasta"
    manifest so_fragmentos
    ;;
  empty)
    # código 0 com um só registro, de 12 pb: so_fragmentos e nada a publicar
    mkdir -p "$saida/fragmentos"
    : > "$saida/contigs.fasta"
    printf '%s\n' "# comentario antes do cabecalho" "$head	faixa" > "$saida/fragmentos/fragmentos.tsv"
    : > "$saida/fragmentos/fragmentos.fasta"
    restricted "f12	12	0					ESPECIFICIDADE_NAO_VALIDADA	<31"
    printf '>f12 len=12\nGGGGGGGGGGGG\n' > "$saida/fragmentos/fragmentos_restritos.fasta"
    manifest so_fragmentos
    ;;
  nokmer)
    manifest sem_kmer_valido
    echo "[genein-builder] ERRO: nenhum k-mer válido de 31 pb nos reads" >&2
    exit 3
    ;;
  norecords)
    mkdir -p "$saida/intermediarios/nucleo"
    manifest sem_registros
    echo "[genein-builder] ERRO: o motor $motor não produziu nenhum registro" >&2
    exit 3
    ;;
  fail)
    echo "builder exploded" >&2
    exit 1
    ;;
  cli)
    echo "builder cli error" >&2
    exit 2
    ;;
esac
MOCK

cat >"$TMP_DIR/bin/spades.py" <<'FAKE_SPADES'
#!/usr/bin/env bash
set -euo pipefail
echo invoked > "${MOCK_SPADES_MARKER:?}"
out=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-o" ]]; then out="$2"; shift 2; else shift; fi
done
mkdir -p "$out"
printf '>long\n%s\n' "$(printf 'T%.0s' {1..300})" > "$out/contigs.fasta"
FAKE_SPADES
cat >"$TMP_DIR/bin/velveth" <<'FAKE_VELVETH'
#!/usr/bin/env bash
set -euo pipefail
[[ -z "${MOCK_VELVET_MARKER:-}" ]] || echo invoked > "$MOCK_VELVET_MARKER"
mkdir -p "$1"
FAKE_VELVETH
cat >"$TMP_DIR/bin/velvetg" <<'FAKE_VELVETG'
#!/usr/bin/env bash
set -euo pipefail
printf '>long\n%s\n' "$(printf 'C%.0s' {1..300})" > "$1/contigs.fa"
FAKE_VELVETG
chmod +x "$TMP_DIR/bin/genein-builder" "$TMP_DIR/bin/spades.py" "$TMP_DIR/bin/velveth" "$TMP_DIR/bin/velvetg"

run_router() {
  local assembler="$1" result="$2"
  local rc=0
  local errexit=0
  case $- in
    *e*) errexit=1 ;;
  esac
  set +e
  PATH="$TMP_DIR/bin:$PATH" \
    PIPELINE_CONFIG_LOADED=1 \
    GENEIN_WORK_ROOT="$TMP_DIR/work" \
    SAMPLE_NAME=BUILDERFIX SAMPLE_ID=BUILDERFIX \
    SAMPLE_R1="$TMP_DIR/R1.fastq.gz" SAMPLE_R2="$TMP_DIR/R2.fastq.gz" \
    ASSEMBLY_DIR="$TMP_DIR/$result" ASSEMBLER="$assembler" THREADS="${THREADS_TEST:-1}" \
    BUILDER_MOTOR="${BUILDER_MOTOR_TEST:-}" \
    GENEIN_BUILDER_VERSION="9.9.9" \
    GENEIN_BUILDER_COMMIT="should-not-stick" \
    MOCK_BUILDER_MODE="${MOCK_BUILDER_MODE:-ok}" \
    MOCK_BUILDER_COMMIT="${MOCK_BUILDER_COMMIT:-$INSTALLED}" \
    MOCK_BUILDER_ARGS="$TMP_DIR/$result.args" \
    MOCK_SPADES_MARKER="$TMP_DIR/$result.spades" \
    MOCK_VELVET_MARKER="$TMP_DIR/$result.velvet" \
    bash scripts/pipeline/assembly_router.sh >"$TMP_DIR/$result.router.log" 2>&1
  rc=$?
  if [[ "$errexit" -eq 1 ]]; then
    set -e
  fi
  return "$rc"
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

no_other_assembler() {
  local result="$1"
  [[ ! -e "$TMP_DIR/$result.spades" ]] || fail "$result: spades foi acionado"
  [[ ! -e "$TMP_DIR/$result.velvet" ]] || fail "$result: velvet foi acionado"
}

MOCK_BUILDER_MODE=ok run_router builder success
META="$TMP_DIR/success/BUILDERFIX_assembly/assembly_metadata.env"
FASTA="$TMP_DIR/success/BUILDERFIX_assembly/contigs.fa"
[[ -s "$FASTA" ]] || fail "success: FASTA canonico vazio"
grep -q 'class=contig|source_id=NODE_1|len=240|faixa=ge200|restricao=nenhuma|k=31|tool=genein-builder' \
  "$FASTA" || fail "success: cabeçalho de contig"
grep -q 'class=fragment|source_id=f36|len=36|faixa=31-49|restricao=ESPECIFICIDADE_NAO_VALIDADA|k=31|tool=genein-builder' \
  "$FASTA" || fail "success: cabeçalho de fragmento"
grep -q 'ASSEMBLER_USED="builder"' "$META"
grep -q 'ASSEMBLER_REQUESTED="builder"' "$META"
grep -q 'ASSEMBLY_FALLBACK=0' "$META"
grep -q 'ASSEMBLY_FAILURE_TYPE="NONE"' "$META"
grep -q 'BUILDER_VERSION="0.4.0"' "$META"
# commit gravado = o do manifesto do Builder instalado, não o fixado no adaptador
grep -q "BUILDER_COMMIT=\"$INSTALLED\"" "$META" || fail "success: commit do manifesto ausente"
grep -q 'BUILDER_MOTOR="v1"' "$META"
grep -q 'BUILDER_STATUS="OK"' "$META"
grep -q 'BUILDER_CONTIG_COUNT="1"' "$META"
grep -q 'BUILDER_FRAGMENT_COUNT="1"' "$META"
grep -q 'BUILDER_DROPPED_LT20="1"' "$META"
if grep -q "should-not-stick\|9\.9\.9\|$PIN" "$META"; then
  fail "success: versao ou commit nao veio do Builder instalado"
fi
grep -qx -- 'run' "$TMP_DIR/success.args" || fail "success: subcomando run ausente"
grep -qx -- '--motor' "$TMP_DIR/success.args" || fail "success: --motor ausente"
grep -qx -- 'v1' "$TMP_DIR/success.args" || fail "success: motor v1 ausente"
if grep -qx -- '--hospedeiro' "$TMP_DIR/success.args"; then
  fail "success: o adaptador nao deve presumir hospedeiro"
fi
grep -qx -- '--r2' "$TMP_DIR/success.args" || fail "success: --r2 ausente na entrada pareada"
grep -qx -- "$TMP_DIR/R1.fastq.gz" "$TMP_DIR/success.args" || fail "success: R1 da fixture nao foi passado"
grep -qx -- "$TMP_DIR/R2.fastq.gz" "$TMP_DIR/success.args" || fail "success: R2 da fixture nao foi passado"
if grep -qx -- '-t' "$TMP_DIR/success.args" || grep -qx -- '--threads' "$TMP_DIR/success.args" \
  || grep -qx -- '--single' "$TMP_DIR/success.args" || grep -qx -- '--fragmentos' "$TMP_DIR/success.args"; then
  fail "success: -t, --threads, --single ou --fragmentos foi passado com o v1"
fi
python3 scripts/lib/input_validation.py fasta "$FASTA" >/dev/null
python3 - "$FASTA" <<'PY'
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
sequences = [line for line in text.splitlines() if not line.startswith(">")]
assert "G" * 12 not in text
assert text.count(">") == 2
# o contig de 240 pb está em contigs.fasta e em fragmentos/: publicado uma vez só
assert sequences.count("A" * 240) == 1, sequences
assert len(set(sequences)) == len(sequences)
PY

BUILDER_MOTOR_TEST=megahit THREADS_TEST=3 MOCK_BUILDER_MODE=ok run_router builder megahit
META="$TMP_DIR/megahit/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'ASSEMBLY_FAILURE_TYPE="NONE"' "$META" || fail "megahit: montagem deveria concluir"
grep -q 'BUILDER_MOTOR="megahit"' "$META" || fail "megahit: motor nao gravado"
grep -q 'BUILDER_K="NA"' "$META" || fail "megahit: k=31 nao vale para o MEGAHIT"
grep -q '|k=NA|tool=genein-builder' "$TMP_DIR/megahit/BUILDERFIX_assembly/contigs.fa"
[[ "$(paste -sd' ' "$TMP_DIR/megahit.args")" == *"--motor megahit -t 3"* ]] \
  || fail "megahit: THREADS nao virou -t"

MOCK_BUILDER_MODE=fragments run_router builder fragments
META="$TMP_DIR/fragments/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'ASSEMBLY_FAILURE_TYPE="NONE"' "$META" \
  || fail "fragments: sequencia de 36 pb nao deveria cair no limiar de 200 pb"
grep -q 'class=fragment|source_id=f36|len=36' "$TMP_DIR/fragments/BUILDERFIX_assembly/contigs.fa"
grep -q 'BUILDER_STATUS="SO_FRAGMENTOS"' "$META" || fail "fragments: status do manifesto"
grep -q 'BUILDER_CONTIG_COUNT="0"' "$META"
grep -q 'BUILDER_FRAGMENT_COUNT="1"' "$META"

MOCK_BUILDER_MODE=empty run_router builder empty
META="$TMP_DIR/empty/BUILDERFIX_assembly/assembly_metadata.env"
[[ -f "$TMP_DIR/empty/BUILDERFIX_assembly/contigs.fa" && ! -s "$TMP_DIR/empty/BUILDERFIX_assembly/contigs.fa" ]] \
  || fail "empty: FASTA canonico deveria existir e estar vazio"
grep -q 'ASSEMBLY_FAILURE_TYPE="SOFT"' "$META"
grep -q 'BUILDER_STATUS="SO_FRAGMENTOS"' "$META"
grep -q 'BUILDER_DROPPED_LT20="1"' "$META"
grep -q 'ASSEMBLY_FALLBACK=0' "$META"
grep -q 'ASSEMBLER_USED="builder"' "$META"
grep -q 'saida vazia fica registrada' "$TMP_DIR/work/logs/assembly/BUILDERFIX_builder.stderr.log" \
  || fail "empty: aviso explicito ausente"
no_other_assembler empty

# Código 3 (decisão 2f): falha, com o status do manifesto e sem outro montador.
for case_status in nokmer:SEM_KMER_VALIDO norecords:SEM_REGISTROS; do
  mode="${case_status%%:*}"
  status="${case_status#*:}"
  set +e
  MOCK_BUILDER_MODE="$mode" run_router builder "$mode"
  code3_rc=$?
  set -e
  META="$TMP_DIR/$mode/BUILDERFIX_assembly/assembly_metadata.env"
  [[ "$code3_rc" -ne 0 ]] || fail "$mode: roteador deveria falhar"
  grep -q 'ASSEMBLY_FAILURE_TYPE="HARD"' "$META"
  grep -q 'ASSEMBLY_FALLBACK=0' "$META"
  grep -q 'ASSEMBLER_USED="builder"' "$META"
  grep -q "BUILDER_STATUS=\"$status\"" "$META" || fail "$mode: BUILDER_STATUS deveria ser $status"
  grep -q "BUILDER_COMMIT=\"$INSTALLED\"" "$META" || fail "$mode: commit do manifesto ausente"
  grep -q 'Nenhum fallback' "$TMP_DIR/$mode.router.log" || fail "$mode: aviso de ausencia de fallback"
  [[ -f "$TMP_DIR/$mode/BUILDERFIX_builder/builder_raw/manifesto_execucao.json" ]] \
    || fail "$mode: manifesto do Builder nao foi preservado"
  no_other_assembler "$mode"
done

set +e
MOCK_BUILDER_MODE=fail run_router builder hard
hard_rc=$?
set -e
[[ "$hard_rc" -ne 0 ]] || fail "hard: roteador deveria falhar"
grep -q 'ASSEMBLY_FAILURE_TYPE="HARD"' "$TMP_DIR/hard/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'ASSEMBLY_FALLBACK=0' "$TMP_DIR/hard/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'ASSEMBLER_USED="builder"' "$TMP_DIR/hard/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'BUILDER_STATUS="FAILED"' "$TMP_DIR/hard/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'Nenhum fallback' "$TMP_DIR/hard.router.log" || fail "hard: aviso de ausencia de fallback"
no_other_assembler hard

set +e
MOCK_BUILDER_MODE=cli run_router builder clierr
cli_rc=$?
set -e
[[ "$cli_rc" -ne 0 ]] || fail "cli: roteador deveria falhar"
grep -q 'ASSEMBLY_FAILURE_TYPE="HARD"' "$TMP_DIR/clierr/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'ASSEMBLY_FALLBACK=0' "$TMP_DIR/clierr/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'ASSEMBLER_USED="builder"' "$TMP_DIR/clierr/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'BUILDER_STATUS="FAILED"' "$TMP_DIR/clierr/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'BUILDER_COMMIT="unavailable"' "$TMP_DIR/clierr/BUILDERFIX_assembly/assembly_metadata.env"
no_other_assembler clierr

# BUILDER_MOTOR fora de v1/megahit: erro explicito, sem outro montador.
set +e
BUILDER_MOTOR_TEST=spades run_router builder badmotor
badmotor_rc=$?
set -e
[[ "$badmotor_rc" -ne 0 ]] || fail "badmotor: roteador deveria falhar"
grep -q 'BUILDER_MOTOR deve ser v1 ou megahit' "$TMP_DIR/work/logs/assembly/BUILDERFIX_builder.stderr.log" \
  || fail "badmotor: mensagem ausente"
[[ ! -e "$TMP_DIR/badmotor.args" ]] || fail "badmotor: Builder foi chamado"
no_other_assembler badmotor

# Entrada simples: --r1 e nada de --r2, --single ou -t.
mkdir -p "$TMP_DIR/single"
PATH="$TMP_DIR/bin:$PATH" \
  env -u R1 -u R2 -u SAMPLE_R1 -u SAMPLE_R2 -u BUILDER_MOTOR \
  SAMPLE_SINGLE="$TMP_DIR/R1.fastq.gz" \
  ASSEMBLY_DIR="$TMP_DIR/single" \
  MOCK_BUILDER_MODE=fragments \
  MOCK_BUILDER_COMMIT="$INSTALLED" \
  MOCK_BUILDER_ARGS="$TMP_DIR/single.args" \
  bash scripts/pipeline/assemblers/builder.sh BUILDERFIX 1 \
  >"$TMP_DIR/single.stdout" 2>"$TMP_DIR/single.stderr"
grep -qx -- '--r1' "$TMP_DIR/single.args" || fail "single: --r1 ausente"
grep -qx -- "$TMP_DIR/R1.fastq.gz" "$TMP_DIR/single.args" || fail "single: caminho de R1 ausente"
if grep -qx -- '--hospedeiro' "$TMP_DIR/single.args"; then
  fail "single: o adaptador nao deve presumir hospedeiro"
fi
if grep -qx -- '--r2' "$TMP_DIR/single.args" \
  || grep -qx -- '--single' "$TMP_DIR/single.args" \
  || grep -qx -- '-t' "$TMP_DIR/single.args"; then
  fail "single: --r2, --single ou -t foi passado"
fi
grep -q 'class=fragment|source_id=f36|len=36' "$TMP_DIR/single/BUILDERFIX_builder/contigs.fasta"

# Sem o executavel simulado e sem o modulo, o erro de instalacao fica explicito.
PYTHON_BIN_DIR="$(dirname "$(command -v python3)")"
if PATH="${PYTHON_BIN_DIR}:/usr/bin:/bin" python3 -c 'import genein_builder_cli' 2>/dev/null; then
  echo "[SKIP] missing: genein_builder_cli importavel neste python3; caso de pacote ausente nao verificado aqui."
else
  set +e
  PATH="${PYTHON_BIN_DIR}:/usr/bin:/bin" \
    PIPELINE_CONFIG_LOADED=1 \
    GENEIN_WORK_ROOT="$TMP_DIR/work" \
    SAMPLE_NAME=BUILDERFIX SAMPLE_ID=BUILDERFIX \
    SAMPLE_R1="$TMP_DIR/R1.fastq.gz" SAMPLE_R2="$TMP_DIR/R2.fastq.gz" \
    ASSEMBLY_DIR="$TMP_DIR/missing" ASSEMBLER=builder THREADS=1 \
    env -u GENEIN_BUILDER_BIN -u GENEIN_BUILDER_VERSION -u GENEIN_BUILDER_COMMIT -u BUILDER_MOTOR \
    bash scripts/pipeline/assembly_router.sh >"$TMP_DIR/missing.router.log" 2>&1
  missing_rc=$?
  set -e
  [[ "$missing_rc" -ne 0 ]] || fail "missing: roteador deveria falhar"
  grep -q 'nao esta instalado' "$TMP_DIR/work/logs/assembly/BUILDERFIX_builder.stderr.log" \
    || fail "missing: mensagem de instalacao ausente"
  grep -q 'ASSEMBLY_FAILURE_TYPE="HARD"' "$TMP_DIR/missing/BUILDERFIX_assembly/assembly_metadata.env"
  grep -q 'ASSEMBLY_FALLBACK=0' "$TMP_DIR/missing/BUILDERFIX_assembly/assembly_metadata.env"
  grep -q 'ASSEMBLER_USED="builder"' "$TMP_DIR/missing/BUILDERFIX_assembly/assembly_metadata.env"
  grep -q 'BUILDER_STATUS="MISSING"' "$TMP_DIR/missing/BUILDERFIX_assembly/assembly_metadata.env"
  grep -q 'BUILDER_COMMIT="unavailable"' "$TMP_DIR/missing/BUILDERFIX_assembly/assembly_metadata.env"
  grep -q 'BUILDER_VERSION="unavailable"' "$TMP_DIR/missing/BUILDERFIX_assembly/assembly_metadata.env"
fi

# O caminho velvet nao ganha chaves do builder.
PATH="$TMP_DIR/bin:$PATH" \
  PIPELINE_CONFIG_LOADED=1 \
  GENEIN_WORK_ROOT="$TMP_DIR/work" \
  SAMPLE_NAME=BUILDERFIX SAMPLE_ID=BUILDERFIX \
  SAMPLE_R1="$TMP_DIR/R1.fastq.gz" SAMPLE_R2="$TMP_DIR/R2.fastq.gz" \
  ASSEMBLY_DIR="$TMP_DIR/velvet" ASSEMBLER=velvet THREADS=1 \
  bash scripts/pipeline/assembly_router.sh >"$TMP_DIR/velvet.router.log" 2>&1
grep -q 'ASSEMBLER_USED="velvet"' "$TMP_DIR/velvet/BUILDERFIX_assembly/assembly_metadata.env"
grep -q 'ASSEMBLY_FAILURE_TYPE="NONE"' "$TMP_DIR/velvet/BUILDERFIX_assembly/assembly_metadata.env"
if grep -q 'BUILDER_' "$TMP_DIR/velvet/BUILDERFIX_assembly/assembly_metadata.env"; then
  fail "velvet: metadata ganhou campo BUILDER_"
fi

echo "PASS builder arm 0.4.0: publicacao sem duplicata, status e commit do manifesto, motor, codigo 3 sem fallback, pacote ausente e metadata velvet intacta"
