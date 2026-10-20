#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"

INCOMING_HOST_FILTER_ENABLED="${HOST_FILTER_ENABLED:-}"
INCOMING_HOST_NAME="${HOST_NAME:-}"
INCOMING_HOST_INDEX_PREFIX="${HOST_INDEX_PREFIX:-}"
INCOMING_HOST_REMOVED_DIR="${HOST_REMOVED_DIR:-}"
INCOMING_RAW_DIR="${RAW_DIR:-}"
INCOMING_THREADS="${THREADS:-}"
INCOMING_HOST_MIN_ALIGNMENT_RATE="${HOST_MIN_ALIGNMENT_RATE:-}"
# HOST_EXPECTED distingue se o hospedeiro declarado deve mesmo estar presente
# na amostra. Segue exatamente o mesmo contrato leve de HOST_MIN_ALIGNMENT_RATE
# acima (variavel de ambiente com default no proprio script, sem passar pelo
# resolvedor JSON) em vez de uma segunda fonte de verdade: as duas afinam o
# mesmo alarme de taxa de alinhamento, entao seguem a mesma convencao.
INCOMING_HOST_EXPECTED="${HOST_EXPECTED:-}"

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
LEGACY_CONFIG="${REPO_ROOT}/config.env"
if [[ "${PIPELINE_CONFIG_LOADED:-0}" != "1" ]]; then
  if [[ -f "${CONFIG_FILE}" ]]; then
    # User config/generated metadata is resolved at runtime.
    # shellcheck disable=SC1090
    source "${CONFIG_FILE}"
  fi
fi

if [[ -n "$INCOMING_HOST_FILTER_ENABLED" ]]; then
  HOST_FILTER_ENABLED="$INCOMING_HOST_FILTER_ENABLED"
fi
if [[ -n "$INCOMING_HOST_NAME" ]]; then
  HOST_NAME="$INCOMING_HOST_NAME"
fi
if [[ -n "$INCOMING_HOST_INDEX_PREFIX" ]]; then
  HOST_INDEX_PREFIX="$INCOMING_HOST_INDEX_PREFIX"
fi
if [[ -n "$INCOMING_HOST_REMOVED_DIR" ]]; then
  HOST_REMOVED_DIR="$INCOMING_HOST_REMOVED_DIR"
fi
if [[ -n "$INCOMING_RAW_DIR" ]]; then
  RAW_DIR="$INCOMING_RAW_DIR"
fi
if [[ -n "$INCOMING_THREADS" ]]; then
  THREADS="$INCOMING_THREADS"
fi
if [[ -n "$INCOMING_HOST_MIN_ALIGNMENT_RATE" ]]; then
  HOST_MIN_ALIGNMENT_RATE="$INCOMING_HOST_MIN_ALIGNMENT_RATE"
fi
if [[ -n "$INCOMING_HOST_EXPECTED" ]]; then
  HOST_EXPECTED="$INCOMING_HOST_EXPECTED"
fi

source "${SCRIPTS_ROOT}/lib/common.sh"
source "${SCRIPTS_ROOT}/lib/host_filter.sh"

if [[ $# -lt 1 ]]; then
  log_error "Uso: $0 NOME_AMOSTRA"
fi

SAMPLE="$1"
SAMPLE="$(python3 "${SCRIPTS_ROOT}/lib/input_validation.py" sample "$SAMPLE")"
SAMPLE_NAME="$SAMPLE"
export SAMPLE_NAME
THREADS="${THREADS:-$(nproc --all 2>/dev/null || echo 4)}"
HOST_MIN_ALIGNMENT_RATE="${HOST_MIN_ALIGNMENT_RATE:-50}"
# Default conservador e retrocompativel: configuracoes antigas que nunca
# declararam HOST_EXPECTED continuam com o comportamento de hoje (taxa de
# alinhamento baixa aborta a amostra, tratada como possivel indice/host
# errado). So quando HOST_EXPECTED=false o alarme de taxa baixa deixa de
# abortar; a saturacao total pelo hospedeiro (nenhum par sobrevive) nao muda
# em nenhum dos dois casos -- ela e tratada abaixo, nas funcoes
# validate_staged_pair/promote_staged_single, independente de HOST_EXPECTED.
HOST_EXPECTED="${HOST_EXPECTED:-true}"
case "${HOST_EXPECTED,,}" in
  true|1|yes|sim) HOST_EXPECTED=true ;;
  false|0|no|nao) HOST_EXPECTED=false ;;
  *) log_error "HOST_EXPECTED invalido: use true/false (ou 1/0, yes/no, sim/nao)." ;;
esac
export HOST_EXPECTED
HOST_FILTER_ENABLED="${HOST_FILTER_ENABLED:-false}"
HOST_NAME="${HOST_NAME:-}"
[[ "$THREADS" =~ ^[1-9][0-9]*$ ]] || log_error "THREADS deve ser inteiro positivo."
if [[ ! "$HOST_MIN_ALIGNMENT_RATE" =~ ^([0-9]+([.][0-9]+)?|[.][0-9]+)$ ]] || \
   ! awk -v value="$HOST_MIN_ALIGNMENT_RATE" 'BEGIN {exit !(value >= 0 && value <= 100)}'; then
  log_error "HOST_MIN_ALIGNMENT_RATE deve ser número entre 0 e 100."
fi

RAW_DIR="$(resolve_path "${RAW_DIR:-data/raw}")"
HOST_REMOVED_DIR="$(resolve_path "${HOST_REMOVED_DIR:-data/host_removed}")"
HOST_INDEX_PREFIX="${HOST_INDEX_PREFIX:-}"

SINGLE=""
if [[ -n "${SAMPLE_SINGLE:-}" && ( -n "${SAMPLE_R1:-}" || -n "${SAMPLE_R2:-}" ) ]]; then
  log_error "Use SAMPLE_SINGLE ou SAMPLE_R1/SAMPLE_R2, mas não ambos."
fi
if [[ -z "${SAMPLE_SINGLE:-}" && ( -n "${SAMPLE_R1:-}" || -n "${SAMPLE_R2:-}" ) && \
   ( -z "${SAMPLE_R1:-}" || -z "${SAMPLE_R2:-}" ) ]]; then
  log_error "Entradas pareadas explícitas exigem SAMPLE_R1 e SAMPLE_R2."
fi
if [[ -n "${SAMPLE_SINGLE:-}" ]]; then
  SINGLE="$(resolve_path "${SAMPLE_SINGLE}")"
  check_file "$SINGLE"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$SINGLE" >/dev/null
else
  if [[ -n "${SAMPLE_R1:-}" ]]; then
    R1="$(resolve_path "${SAMPLE_R1}")"
  else
    R1="${RAW_DIR}/${SAMPLE}_R1.fastq.gz"
  fi
  if [[ -n "${SAMPLE_R2:-}" ]]; then
    R2="$(resolve_path "${SAMPLE_R2}")"
  else
    R2="${RAW_DIR}/${SAMPLE}_R2.fastq.gz"
  fi
  check_file "$R1"
  check_file "$R2"
  python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$R1" --mate "$R2" >/dev/null
fi

case "${HOST_FILTER_ENABLED,,}" in
  false|0|no|nao)
    log_info "Filtro de hospedeiro desabilitado; nenhuma saída será rotulada como host_removed."
    exit 0
    ;;
  true|1|yes|sim)
    HOST_FILTER_ENABLED=true
    ;;
  *)
    log_error "HOST_FILTER_ENABLED inválido: use true/false (ou 1/0, yes/no, sim/nao)."
    ;;
esac

[[ -n "$HOST_NAME" ]] || log_error "HOST_FILTER_ENABLED=true exige HOST_NAME explícito."
[[ -n "$HOST_INDEX_PREFIX" ]] || log_error "HOST_FILTER_ENABLED=true exige HOST_INDEX_PREFIX explícito."
HOST_INDEX_PREFIX="$(resolve_path "$HOST_INDEX_PREFIX")"
if ! INDEX_KIND="$(validate_bt2_index "$HOST_INDEX_PREFIX")"; then
  log_error "Falha na validacao do indice do hospedeiro '${HOST_NAME}' em ${HOST_INDEX_PREFIX}."
fi
command -v bowtie2 >/dev/null 2>&1 || log_error "bowtie2 não encontrado no PATH."

if [[ ! -d "$HOST_REMOVED_DIR" ]]; then
  mkdir -p "$HOST_REMOVED_DIR"
fi

OUT_R1="${HOST_REMOVED_DIR}/${SAMPLE}_R1.host_removed.fastq.gz"
OUT_R2="${HOST_REMOVED_DIR}/${SAMPLE}_R2.host_removed.fastq.gz"
OUT_SINGLE="${HOST_REMOVED_DIR}/${SAMPLE}.host_removed.fastq.gz"
WORK_DIR="$(mktemp -d "${HOST_REMOVED_DIR}/.${SAMPLE}.host-filter.XXXXXX")"
cleanup() {
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

# Saída vazia é um desfecho possível (toda a leitura alinhou ao hospedeiro).
# Diferente de um FASTQ corrompido ou despareado (que continuam sendo erro),
# a saturação total pelo hospedeiro é um desfecho reconhecido: nenhum FASTQ
# vazio é promovido, mas o script termina com exit code 0 e um marcador
# estruturado e durável, para que sample_steps.sh encerre a amostra de forma
# limpa em vez de tratar isso como falha de ferramenta.
host_filter_output_is_empty() {
  local path="$1"
  gzip -t "$path" 2>/dev/null || return 1
  [[ "$(gzip -cd "$path" | wc -c)" -eq 0 ]]
}

HOST_SATURATION_MARKER="${HOST_REMOVED_DIR}/${SAMPLE}.host_saturation.json"
HOST_SATURATED=0
# Never let a prior successful run make a current Bowtie2 failure look like
# saturation. This marker belongs to the current filtering attempt only.
rm -f -- "$HOST_SATURATION_MARKER"

write_host_saturation_marker() {
  local mode="$1"
  python3 - "$HOST_SATURATION_MARKER" "$SAMPLE" "$HOST_NAME" "$HOST_INDEX_PREFIX" "$mode" "$BT2_LOG" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

out_path, sample, host_name, host_index_prefix, mode, bt2_log = sys.argv[1:7]
payload = {
    "schema_version": "1.0",
    "host_saturated": True,
    "sample": sample,
    "host_name": host_name,
    "host_expected": os.environ.get("HOST_EXPECTED", "true"),
    "host_index_prefix": host_index_prefix,
    "mode": mode,
    "bowtie2_log": bt2_log,
    "detected_at": datetime.now(timezone.utc).isoformat(),
}
tmp_path = f"{out_path}.tmp.{os.getpid()}"
with open(tmp_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(tmp_path, out_path)
try:
    directory_fd = os.open(os.path.dirname(out_path) or ".", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
except OSError:
    directory_fd = None  # Some mounted filesystems do not expose directory fsync.
if directory_fd is not None:
    try:
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        os.close(directory_fd)
PY
}

validate_staged_pair() {
  local staged_r1="$1"
  local staged_r2="$2"
  if [[ ! -f "$staged_r1" || ! -f "$staged_r2" ]]; then
    log_error "Filtro de hospedeiro nao produziu o par de FASTQs esperado."
  fi
  if ! gzip -t "$staged_r1" "$staged_r2"; then
    log_error "FASTQs produzidos pelo filtro de hospedeiro estao corrompidos."
  fi
  if host_filter_output_is_empty "$staged_r1" && host_filter_output_is_empty "$staged_r2"; then
    write_host_saturation_marker "paired"
    HOST_SATURATED=1
    log_info "Saturacao total pelo hospedeiro '${HOST_NAME}': todas as leituras (ambos os mates) alinharam ao indice ${HOST_INDEX_PREFIX}. Nenhuma saida vazia foi promovida; marcador de saturacao registrado em ${HOST_SATURATION_MARKER}."
    return 0
  fi
  if ! python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$staged_r1" \
    --mate "$staged_r2" >/dev/null; then
    log_error "FASTQs produzidos pelo filtro de hospedeiro são vazios ou não formam pares válidos."
  fi
}

promote_staged_single() {
  local staged="$1"
  local previous="${WORK_DIR}/previous_single.fastq.gz"
  local had_previous=0
  # Bowtie2 may omit --un-gz when zero single-end reads remain. Require
  # the successful run's exact unmapped-read count, not rounded percentage alone.
  local confirmed_zero_unaligned=0
  if [[ ! -e "$staged" ]] && python3 - "$BT2_LOG" <<'PY'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
totals = re.findall(r"^\s*(\d+) reads; of these:\s*$", text, re.M)
unpaired = re.findall(r"^\s*(\d+) \([\d.]+%\) were unpaired; of these:\s*$", text, re.M)
unaligned = re.findall(r"^\s*(\d+) \([\d.]+%\) aligned 0 times\s*$", text, re.M)
rates = re.findall(r"^\s*([\d.]+)% overall alignment rate\s*$", text, re.M)
valid = (len(totals) == len(unpaired) == len(unaligned) == len(rates) == 1
         and int(totals[0]) > 0 and int(unpaired[0]) == int(totals[0])
         and int(unaligned[0]) == 0 and float(rates[0]) == 100.0)
sys.exit(0 if valid else 1)
PY
  then
    confirmed_zero_unaligned=1
  fi
  if [[ "$confirmed_zero_unaligned" -eq 1 ]] || { [[ -f "$staged" ]] && host_filter_output_is_empty "$staged"; }; then
    write_host_saturation_marker "single"
    HOST_SATURATED=1
    log_info "Saturacao total pelo hospedeiro '${HOST_NAME}': todas as leituras alinharam ao indice ${HOST_INDEX_PREFIX}. Nenhuma saida vazia foi promovida; marcador de saturacao registrado em ${HOST_SATURATION_MARKER}."
    return 0
  fi
  if [[ ! -f "$staged" ]] || ! gzip -t "$staged" || \
     ! python3 "${SCRIPTS_ROOT}/lib/input_validation.py" fastq "$staged" >/dev/null; then
    log_error "Filtro de hospedeiro não produziu um FASTQ single-end válido."
  fi
  if [[ -e "$OUT_SINGLE" ]]; then
    mv "$OUT_SINGLE" "$previous"
    had_previous=1
  fi
  if mv "$staged" "$OUT_SINGLE"; then
    return 0
  fi
  if [[ $had_previous -eq 1 ]]; then
    mv "$previous" "$OUT_SINGLE"
  fi
  log_error "Falha ao promover FASTQ single-end filtrado; a saída anterior foi restaurada."
}

promote_staged_pair() {
  local staged_r1="$1"
  local staged_r2="$2"
  local previous_r1="${WORK_DIR}/previous_R1.fastq.gz"
  local previous_r2="${WORK_DIR}/previous_R2.fastq.gz"
  local had_previous_r1=0
  local had_previous_r2=0

  validate_staged_pair "$staged_r1" "$staged_r2"
  if [[ "$HOST_SATURATED" -eq 1 ]]; then
    return 0
  fi

  if [[ -e "$OUT_R1" ]]; then
    mv "$OUT_R1" "$previous_r1"
    had_previous_r1=1
  fi
  if [[ -e "$OUT_R2" ]]; then
    if ! mv "$OUT_R2" "$previous_r2"; then
      if [[ $had_previous_r1 -eq 1 ]]; then
        mv "$previous_r1" "$OUT_R1"
      fi
      log_error "Nao foi possivel iniciar a promocao transacional dos FASTQs filtrados."
    fi
    had_previous_r2=1
  fi

  if mv "$staged_r1" "$OUT_R1" && mv "$staged_r2" "$OUT_R2"; then
    return 0
  fi

  rm -f -- "$OUT_R1" "$OUT_R2"
  if [[ $had_previous_r1 -eq 1 ]]; then
    mv "$previous_r1" "$OUT_R1"
  fi
  if [[ $had_previous_r2 -eq 1 ]]; then
    mv "$previous_r2" "$OUT_R2"
  fi
  log_error "Falha ao promover FASTQs filtrados; o par anterior foi restaurado."
}

BT2_LOG="${HOST_REMOVED_DIR}/${SAMPLE}_host_filter_bowtie2.log"

log_info "Filtrando leituras do hospedeiro (${HOST_NAME}) para amostra ${SAMPLE} usando indice ${INDEX_KIND} e ${THREADS} thread(s)..."

if [[ -n "$SINGLE" ]]; then
  if ! bowtie2 \
    -x "$HOST_INDEX_PREFIX" -U "$SINGLE" \
    --very-sensitive -p "$THREADS" \
    --un-gz "${WORK_DIR}/single.fastq.gz" \
    -S /dev/null 2> "$BT2_LOG"; then
    log_error "Bowtie2 falhou durante filtro single-end do hospedeiro. Veja o log: ${BT2_LOG}"
  fi
else
  command -v samtools >/dev/null 2>&1 || log_error "samtools não encontrado no PATH."
  if ! bowtie2 \
    -x "$HOST_INDEX_PREFIX" -1 "$R1" -2 "$R2" \
    --very-sensitive -p "$THREADS" 2> "$BT2_LOG" \
    | samtools view -b -f 12 -F 256 - \
    | samtools sort -n -@ "$THREADS" -T "${WORK_DIR}/name-sort" - \
    | samtools fastq -1 "${WORK_DIR}/R1.fastq" -2 "${WORK_DIR}/R2.fastq" \
        -0 /dev/null -s /dev/null -n - 2>> "$BT2_LOG"; then
    log_error "Bowtie2/samtools falhou durante filtro pareado do hospedeiro. Veja o log: ${BT2_LOG}"
  fi
  gzip -c "${WORK_DIR}/R1.fastq" > "${WORK_DIR}/R1.fastq.gz"
  gzip -c "${WORK_DIR}/R2.fastq" > "${WORK_DIR}/R2.fastq.gz"
fi

alignment_rate="$(awk '/overall alignment rate/ {gsub("%", "", $1); print $1}' "$BT2_LOG" | tail -n 1)"
if [[ -n "$alignment_rate" ]]; then
  low_rate="$(awk -v rate="$alignment_rate" -v min="$HOST_MIN_ALIGNMENT_RATE" 'BEGIN {print (rate < min) ? 1 : 0}')"
  if [[ "$low_rate" == "1" ]]; then
    if [[ "$HOST_EXPECTED" == "true" ]]; then
      log_error "Taxa de alinhamento ao hospedeiro baixa (${alignment_rate}%; minimo ${HOST_MIN_ALIGNMENT_RATE}%). Possivel referencia incompleta ou indice incorreto: ${HOST_INDEX_PREFIX}"
    else
      log_warning "Taxa de alinhamento ao hospedeiro baixa (${alignment_rate}%; minimo ${HOST_MIN_ALIGNMENT_RATE}%), mas HOST_EXPECTED=false: hospedeiro nao e esperado nesta amostra, entao a taxa baixa nao aborta a execucao. Prosseguindo com as leitura(s) nao alinhada(s) ao indice ${HOST_INDEX_PREFIX}."
    fi
  fi
else
  log_warning "Nao foi possivel ler a taxa de alinhamento do Bowtie2 em ${BT2_LOG}."
fi

if [[ -n "$SINGLE" ]]; then
  promote_staged_single "${WORK_DIR}/single.fastq.gz"
  if [[ "$HOST_SATURATED" -eq 0 ]]; then
    log_info "Leituras single-end não alinhadas ao hospedeiro salvas em ${OUT_SINGLE}"
  fi
else
  promote_staged_pair "${WORK_DIR}/R1.fastq.gz" "${WORK_DIR}/R2.fastq.gz"
  if [[ "$HOST_SATURATED" -eq 0 ]]; then
    log_info "Pares em que ambos os mates não alinharam ao hospedeiro salvos em:"
    echo "  ${OUT_R1}"
    echo "  ${OUT_R2}"
  fi
fi
# Saturacao total (HOST_SATURATED=1) e corrupcao/erro de ferramenta continuam
# distintos: corrupcao e arquivo ausente permanecem log_error (exit 1) nas
# funcoes acima; apenas a saturacao reconhecida chega aqui e sai com exit 0.
exit 0
