#!/usr/bin/env bash
# Canonical FASTQ → QC → opt-in host filter → assembly/rescue → BLAST → Evidence V2.
# Uses real tools and versioned synthetic fixtures. Not scientific validation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

for command_name in python3 fastp spades.py blastn blastdbcmd makeblastdb; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "SKIP: $command_name is not installed"
    exit 77
  }
done

FIXTURE_DIR="$ROOT/scripts/tests/fixtures/pipeline_e2e"
TARGET_FA="$FIXTURE_DIR/target.fa"
LABELS_TSV="$FIXTURE_DIR/labels.tsv"
[[ -s "$TARGET_FA" && -s "$LABELS_TSV" ]] || {
  echo "SKIP: versioned pipeline_e2e fixtures are missing" >&2
  exit 77
}

mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
WORK="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-e4-e2e.XXXXXX")"
SAMPLE_R="e4canonR"
SAMPLE_N="e4canonN"
SAMPLE_F="e4canonF"
RUN_R="e4canonR1run"
RUN_N="e4canonN1run"
RUN_F="e4canonF1run"

cleanup() {
  local status=$?
  if [[ "$status" -ne 0 || -n "${GENEIN_TEST_ARTIFACT_ROOT:-}" ]]; then
    echo "[ARTIFACTS] $WORK (exit=$status)" >&2
  else
    case "$WORK" in /tmp/genein-e4-e2e.*) rm -rf -- "$WORK" ;; esac
  fi
}
trap cleanup EXIT

BLAST_PREFIX="$WORK/blastdb/e4target"
EVIDENCE_ROOT="$WORK/evidence"
FASTQ_DIR="$WORK/fastq"
mkdir -p "$WORK/pipeline" "$WORK/blastdb" "$EVIDENCE_ROOT" "$FASTQ_DIR" "$WORK/versions"

{
  echo "python3 $(python3 --version 2>&1)"
  echo "fastp $(fastp --version 2>&1 | head -n 1)"
  echo "spades.py $(spades.py --version 2>&1 | head -n 1)"
  echo "blastn $(blastn -version 2>&1 | head -n 1)"
  echo "makeblastdb $(makeblastdb -version 2>&1 | head -n 1)"
} > "$WORK/versions/tools.txt"
cat "$WORK/versions/tools.txt"

cp "$TARGET_FA" "$WORK/target.fa"
TARGET_FA="$WORK/target.fa"
makeblastdb -in "$TARGET_FA" -dbtype nucl -parse_seqids -out "$BLAST_PREFIX" >/dev/null
python3 - "$TARGET_FA" "$BLAST_PREFIX" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

reference = Path(sys.argv[1])
prefix = Path(sys.argv[2])
produced = sorted(
    path for path in prefix.parent.glob(f"{prefix.name}.*")
    if path.is_file() and not path.name.endswith(".db-manifest.json")
)

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

manifest = {
    "schema_version": "1.0",
    "logical_prefix": str(prefix),
    "generation_id": "e4-synthetic-20260825",
    "created_at": "2026-08-25T00:00:00+00:00",
    "source_fasta": {
        "path": str(reference),
        "size": reference.stat().st_size,
        "sha256": sha256(reference),
    },
    "produced_files": {
        path.name: {"size": path.stat().st_size, "sha256": sha256(path)}
        for path in produced
    },
}
Path(f"{prefix}.db-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

python3 scripts/ops/make_demo_fastq.py \
  --ref "$TARGET_FA" --outdir "$FASTQ_DIR" --sample "$SAMPLE_R" \
  --pairs 300 --len 150 --insert 300 --seed 20260825 >/dev/null
python3 scripts/ops/make_demo_fastq.py \
  --random --outdir "$FASTQ_DIR" --sample "$SAMPLE_N" \
  --pairs 80 --len 150 --insert 300 --seed 20260825 >/dev/null
cp -f "$FASTQ_DIR/${SAMPLE_R}_R1.fastq.gz" "$FASTQ_DIR/${SAMPLE_F}_R1.fastq.gz"
cp -f "$FASTQ_DIR/${SAMPLE_R}_R2.fastq.gz" "$FASTQ_DIR/${SAMPLE_F}_R2.fastq.gz"

run_canonical() {
  local sample="$1"
  local run_id="$2"
  local extra_env=()
  if [[ -n "${3:-}" ]]; then
    extra_env+=("EVIDENCE_COMPOSITE_DB=$3")
    extra_env+=("EVIDENCE_SUBJECT_LABELS=${EVIDENCE_SUBJECT_LABELS_OVERRIDE:-$LABELS_TSV}")
  fi
  env -u DB -u DB_QUERY -u REF_FASTA -u BOWTIE2_INDEX \
    GENEIN_WORK_ROOT="$WORK/pipeline" \
    HOST_FILTER_ENABLED=false \
    BLAST_DB="$BLAST_PREFIX" \
    EVIDENCE_V2=true \
    EVIDENCE_ROOT="$EVIDENCE_ROOT" \
    EVIDENCE_RUN_ID="$run_id" \
    SAMPLE_R1="$FASTQ_DIR/${sample}_R1.fastq.gz" \
    SAMPLE_R2="$FASTQ_DIR/${sample}_R2.fastq.gz" \
    QC_OUT_DIR="$WORK/cleaned" \
    QC_REPORT_DIR="$WORK/qc" \
    "${extra_env[@]}" \
    bash "$ROOT/scripts/pipeline/run.sh" \
      --sample "$sample" \
      --analysis-profile default \
      --assembler spades \
      --threads 2 \
      --spades-params "-m 4 --phred-offset 33" \
      --evidence-v2 \
      --evidence-root "$EVIDENCE_ROOT"
}

assert_json() {
  python3 - "$@" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected_outcome = sys.argv[2]
require_success = sys.argv[3] == "success"
success = root / "SUCCESS.json"
staging = root.parent.parent / ".staging" / root.name
if require_success:
    if not success.is_file():
        raise SystemExit(f"missing SUCCESS.json in {root}")
    if staging.exists():
        raise SystemExit(f"staging was not cleared after promotion: {staging}")
else:
    if success.is_file():
        raise SystemExit(f"incomplete run wrote SUCCESS.json: {success}")
    promoted = list(root.glob("SUCCESS.json"))
    if promoted:
        raise SystemExit("promoted SUCCESS.json must not exist for NOT_EVALUABLE")

evidence_path = root / "sample_evidence.json"
if not evidence_path.is_file():
    raise SystemExit(f"missing sample_evidence.json in {root}")
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
if evidence["analysis_outcome"] != expected_outcome:
    raise SystemExit(
        f"analysis_outcome={evidence['analysis_outcome']!r} expected {expected_outcome}"
    )
if evidence["shadow_mode"] is not False:
    raise SystemExit("default open-analysis policy must have shadow_mode=false")
if evidence["reported_conclusion"] != expected_outcome:
    raise SystemExit("reported conclusion must preserve the measured analysis outcome")
if evidence.get("promotion_gates"):
    raise SystemExit("the current open-analysis contract has no promotion gates")
if expected_outcome == "NOT_EVALUABLE":
    if evidence["evidence_level"] != "NOT_EVALUABLE":
        raise SystemExit("NOT_EVALUABLE must keep evidence_level=NOT_EVALUABLE")
    if success.is_file():
        raise SystemExit("NOT_EVALUABLE must not write SUCCESS.json")
else:
    if expected_outcome == "EVIDENCE_RECOVERED":
        expected_level = "DETECTED"
    elif expected_outcome == "CANDIDATES_FOR_REVIEW":
        expected_level = "REVIEW"
    else:
        expected_level = "NO_SIGNAL"
    if evidence["evidence_level"] != expected_level:
        raise SystemExit(f"evidence_level must be {expected_level}")
    if "DETECTED" in json.dumps(evidence) and expected_outcome != "EVIDENCE_RECOVERED":
        raise SystemExit("uncontrolled execution must not carry DETECTED")
    if expected_outcome in {"EVIDENCE_RECOVERED", "CANDIDATES_FOR_REVIEW"} and not evidence.get("candidates"):
        raise SystemExit("recovered case lost its computational candidates")
    if expected_outcome == "NO_EVIDENCE_RECOVERED" and evidence.get("candidates"):
        raise SystemExit("negative case must not invent candidates")
print(f"PASS {root.name} {expected_outcome}")
PY
}

echo "[E4] recovered candidate"
run_canonical "$SAMPLE_R" "$RUN_R"
assert_json "$EVIDENCE_ROOT/runs/$RUN_R" CANDIDATES_FOR_REVIEW success
if ! grep -q "HOST_FILTER_ENABLED=false; reads seguem sem etapa Bowtie2 de hospedeiro." \
    "${WORK}/pipeline/logs/${SAMPLE_R}_pipeline.log"; then
  echo "host filter opt-in was not recorded" >&2
  exit 1
fi
if grep -F "scripts/legacy/" "${WORK}/pipeline/logs/${SAMPLE_R}_pipeline.log"; then
  echo "canonical run invoked a legacy script" >&2
  exit 1
fi
if grep -q "Índice completo do hospedeiro" "${WORK}/pipeline/logs/${SAMPLE_R}_pipeline.log"; then
  echo "host filter ran without explicit host selection" >&2
  exit 1
fi

echo "[E4] negative no recovered candidate"
run_canonical "$SAMPLE_N" "$RUN_N"
assert_json "$EVIDENCE_ROOT/runs/$RUN_N" NO_EVIDENCE_RECOVERED success

echo "[E4] controlled failure NOT_EVALUABLE"
# Missing databases now fail before processing. Use missing labels to exercise
# a failure after the Evidence runner has reserved its state and staging.
set +e
EVIDENCE_SUBJECT_LABELS_OVERRIDE="$WORK/missing_labels.tsv" run_canonical "$SAMPLE_F" "$RUN_F" "$BLAST_PREFIX"
FAIL_RC=$?
set -e
echo "[E4] pipeline exit after controlled V2 failure: $FAIL_RC"
[[ "$FAIL_RC" -ne 0 ]] || { echo "controlled failure returned success" >&2; exit 1; }
FAIL_DIR="$EVIDENCE_ROOT/runs/$RUN_F"
FAIL_STAGING="$EVIDENCE_ROOT/.staging/$RUN_F"
FAIL_STATE="$EVIDENCE_ROOT/state/${RUN_F}.json"
if [[ -f "$FAIL_DIR/SUCCESS.json" ]]; then
  echo "controlled failure promoted SUCCESS.json" >&2
  exit 1
fi
if [[ -d "$FAIL_DIR" && -f "$FAIL_DIR/SUCCESS.json" ]]; then
  echo "controlled failure left a consumable promoted run" >&2
  exit 1
fi
if [[ -f "$FAIL_STAGING/sample_evidence.json" ]]; then
  assert_json "$FAIL_STAGING" NOT_EVALUABLE failed
elif [[ -f "$FAIL_DIR/sample_evidence.json" ]]; then
  assert_json "$FAIL_DIR" NOT_EVALUABLE failed
else
  echo "controlled failure did not write NOT_EVALUABLE evidence" >&2
  exit 1
fi
python3 - "$FAIL_STATE" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if state.get("status") not in {"failed", "cancelled"}:
    raise SystemExit(f"unexpected failure status: {state.get('status')}")
if state.get("analysis_outcome") != "NOT_EVALUABLE":
    raise SystemExit(f"state outcome {state.get('analysis_outcome')!r} is not NOT_EVALUABLE")
print("PASS failure state NOT_EVALUABLE")
PY

set +e
env -u DB -u DB_QUERY \
  EVIDENCE_ROOT="$EVIDENCE_ROOT" \
  bash "$ROOT/scripts/evidence/run.sh" \
    --sample "$SAMPLE_F" \
    --queries "$TARGET_FA" \
    --profiles "$ROOT/config/evidence_profiles.json" \
    --evidence-root "$EVIDENCE_ROOT" \
    --run-id "$RUN_F" >/dev/null 2>"$WORK/reuse.err"
REUSE_RC=$?
set -e
if [[ "$REUSE_RC" -eq 0 ]]; then
  echo "failed run_id was reused without success" >&2
  exit 1
fi
if ! grep -q "already has staging or final artifacts" "$WORK/reuse.err" \
    && ! grep -q "already exists" "$WORK/reuse.err"; then
  echo "reuse rejection message missing:" >&2
  cat "$WORK/reuse.err" >&2
  exit 1
fi
echo "PASS staging reuse rejected"

echo "[E4] composite DB absent"
SAMPLE_C="e4canonC"
RUN_C="e4canonC1run"
cp -f "$FASTQ_DIR/${SAMPLE_R}_R1.fastq.gz" "$FASTQ_DIR/${SAMPLE_C}_R1.fastq.gz"
cp -f "$FASTQ_DIR/${SAMPLE_R}_R2.fastq.gz" "$FASTQ_DIR/${SAMPLE_C}_R2.fastq.gz"
mkdir -p "$EVIDENCE_ROOT/state"
python3 "$ROOT/scripts/evidence/run_state.py" \
  --state "$EVIDENCE_ROOT/state/${RUN_C}.json" \
  init --run-id "$RUN_C" --action evidence_single --sample "$SAMPLE_C"
set +e
run_canonical "$SAMPLE_C" "$RUN_C" "$WORK/missing_composite_panel"
ABSENT_RC=$?
set -e
echo "[E4] composite DB absent exit: $ABSENT_RC"
[[ "$ABSENT_RC" -eq 65 ]] || { echo "composite DB absent returned $ABSENT_RC" >&2; exit 1; }
ABSENT_LOG="${WORK}/pipeline/logs/${SAMPLE_C}_pipeline.log"
grep -F "[DATABASE_PREFLIGHT]" "$ABSENT_LOG" >/dev/null || { echo "composite DB absent missing DATABASE_PREFLIGHT" >&2; exit 1; }
grep -F "Banco composto sem manifesto" "$ABSENT_LOG" >/dev/null || { echo "composite DB absent missing manifest message" >&2; exit 1; }
if grep -F "[QC_FASTP]" "$ABSENT_LOG"; then
  echo "composite DB absent reached QC" >&2
  exit 1
fi
python3 - "$EVIDENCE_ROOT/state/${RUN_C}.json" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if state.get("status") != "failed":
    raise SystemExit(f"unexpected status: {state.get('status')}")
if state.get("failed_stage") != "database_preflight":
    raise SystemExit(f"failed_stage={state.get('failed_stage')!r}")
if state.get("failure_type") != "INPUT_INVALID":
    raise SystemExit(f"failure_type={state.get('failure_type')!r}")
quality = next(item for item in state["stages"] if item["id"] == "quality_control")
if quality["status"] != "pending":
    raise SystemExit(f"quality_control status={quality['status']}")
print("PASS composite DB absent database_preflight")
PY
if [[ -e "$EVIDENCE_ROOT/runs/$RUN_C/SUCCESS.json" ]]; then
  echo "composite DB absent promoted SUCCESS.json" >&2
  exit 1
fi

mkdir -p "$WORK/retained-logs"
cp -f "$WORK/versions/tools.txt" "$WORK/retained-logs/software_versions.txt"
for sample in "$SAMPLE_R" "$SAMPLE_N" "$SAMPLE_F" "$SAMPLE_C"; do
  if [[ -f "${WORK}/pipeline/logs/${sample}_pipeline.log" ]]; then
    cp -f "${WORK}/pipeline/logs/${sample}_pipeline.log" "$WORK/retained-logs/${sample}_pipeline.log"
  fi
done

echo "PASS: canonical pipeline FASTQ→QC→host-opt-in→assembly→BLAST→Evidence V2"
echo "VERSIONS_FILE=$WORK/retained-logs/software_versions.txt"
