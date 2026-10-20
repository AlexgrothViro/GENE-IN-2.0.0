#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
if ! git -C "$ROOT" rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "NÃO EXECUTADO: mapeamento direto experimental exige checkout Git; indisponível no ZIP de distribuição."
  exit 77
fi
for command_name in python3 bowtie2 bowtie2-build samtools; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "SKIP: $command_name is not installed"
    exit 77
  }
done

mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
WORK="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-direct-map-e2e.XXXXXX")"
cleanup() {
  local status=$?
  if [[ "$status" -ne 0 || -n "${GENEIN_TEST_ARTIFACT_ROOT:-}" ]]; then
    echo "[ARTIFACTS] $WORK (exit=$status)" >&2
    return
  fi
  case "$WORK" in
    /tmp/genein-direct-map-e2e.*) rm -rf -- "$WORK" ;;
    *) echo "Refusing to remove unexpected test path: $WORK" >&2 ;;
  esac
}
trap cleanup EXIT

python3 "$ROOT/scripts/tests/evidence/generate_direct_map_matrix.py" --out "$WORK/matrix"
bowtie2-build --seed 1729 "$WORK/matrix/panel.fa" "$WORK/matrix/panel" \
  >"$WORK/bowtie2-build.stdout" 2>"$WORK/bowtie2-build.stderr"
python3 - "$WORK/matrix/panel.fa" "$WORK/matrix/divergent-index.fa" <<'PY'
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
Path(sys.argv[2]).write_text(text.replace(">unique_ref\n", ">ref_ghost\n", 1), encoding="utf-8", newline="\n")
PY
bowtie2-build --seed 1729 "$WORK/matrix/divergent-index.fa" "$WORK/matrix/divergent-index" \
  >"$WORK/divergent-build.stdout" 2>"$WORK/divergent-build.stderr"

python3 - "$WORK/matrix/panel_manifest.json" "$WORK/matrix/invalid_panel_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
manifest["schema_version"] = "invalid-panel-schema"
Path(sys.argv[2]).write_text(json.dumps(manifest) + "\n", encoding="utf-8")
PY
if bash "$ROOT/scripts/experimental/direct_map/run.sh" \
  --sample synthetic-direct-map-invalid-panel \
  --run-id direct-map-e2e-invalid-panel \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --reference "$WORK/matrix/panel.fa" \
  --index "$WORK/matrix/panel" \
  --loci "$WORK/matrix/loci.tsv" \
  --single "$WORK/matrix/single.fastq" \
  --panel-manifest "$WORK/matrix/invalid_panel_manifest.json" \
  --umi-mode none \
  --out-root "$WORK/invalid-panel-output" \
  --threads 1 >"$WORK/invalid-panel.stdout" 2>"$WORK/invalid-panel.stderr"; then
  echo "invalid panel manifest unexpectedly reached a successful run" >&2
  exit 1
fi
grep -q "panel manifest must use experimental-direct-map-panel-v1" "$WORK/invalid-panel.stderr" || {
  echo "invalid panel failure did not originate in pre-alignment panel validation" >&2
  exit 1
}
[[ ! -e "$WORK/invalid-panel-output/experimental" ]] || {
  echo "invalid panel validation created an experimental staging directory" >&2
  exit 1
}

if GENEIN_PUBLIC_EVIDENCE_ROOT="$WORK/public-evidence" bash "$ROOT/scripts/experimental/direct_map/run.sh" \
  --sample synthetic-direct-map-isolation \
  --run-id direct-map-e2e-isolation \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --reference "$WORK/matrix/panel.fa" \
  --index "$WORK/matrix/panel" \
  --loci "$WORK/matrix/loci.tsv" \
  --single "$WORK/matrix/single.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json" \
  --umi-mode none \
  --out-root "$WORK/public-evidence" \
  --threads 1 >"$WORK/isolation.stdout" 2>"$WORK/isolation.stderr"; then
  echo "experimental run was not isolated from the public Evidence V2 root" >&2
  exit 1
fi
[[ ! -e "$WORK/public-evidence/experimental" ]] || {
  echo "isolation rejection created an experimental run directory under the public root" >&2
  exit 1
}

bash "$ROOT/scripts/experimental/direct_map/run.sh" \
  --sample synthetic-direct-map \
  --run-id direct-map-e2e-0001 \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --reference "$WORK/matrix/panel.fa" \
  --index "$WORK/matrix/panel" \
  --loci "$WORK/matrix/loci.tsv" \
  --r1 "$WORK/matrix/r1.fastq" \
  --r2 "$WORK/matrix/r2.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json" \
  --umi-mode read_name \
  --out-root "$WORK/output" \
  --threads 2 >/dev/null

bash "$ROOT/scripts/experimental/direct_map/run.sh" \
  --sample synthetic-direct-map \
  --run-id direct-map-e2e-0001 \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --reference "$WORK/matrix/panel.fa" \
  --index "$WORK/matrix/panel" \
  --loci "$WORK/matrix/loci.tsv" \
  --r1 "$WORK/matrix/r1.fastq" \
  --r2 "$WORK/matrix/r2.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json" \
  --umi-mode read_name \
  --out-root "$WORK/output-repeat" \
  --threads 2 >/dev/null

bash "$ROOT/scripts/experimental/direct_map/run.sh" \
  --sample synthetic-direct-map-single \
  --run-id direct-map-e2e-0002 \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --reference "$WORK/matrix/panel.fa" \
  --index "$WORK/matrix/panel" \
  --loci "$WORK/matrix/loci.tsv" \
  --single "$WORK/matrix/single.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json" \
  --umi-mode none \
  --out-root "$WORK/output" \
  --threads 1 >/dev/null

FINAL="$WORK/output/experimental/direct-map-v1/runs/direct-map-e2e-0001"
REPEAT_FINAL="$WORK/output-repeat/experimental/direct-map-v1/runs/direct-map-e2e-0001"
SINGLE_FINAL="$WORK/output/experimental/direct-map-v1/runs/direct-map-e2e-0002"
CONTRACT_RUN_ID="direct-map-e2e-paired-mapq-contract"
CONTRACT_STAGING="$WORK/output/experimental/direct-map-v1/.staging/$CONTRACT_RUN_ID"
CONTRACT_FINAL="$WORK/output/experimental/direct-map-v1/runs/$CONTRACT_RUN_ID"
mkdir -p "$CONTRACT_STAGING"
for pass_name in primary placements; do
  samtools view -b -o "$CONTRACT_STAGING/.${pass_name}.unsorted.tmp" \
    "$WORK/matrix/contract_paired_${pass_name}.sam"
  samtools sort -o "$CONTRACT_STAGING/${pass_name}.bam" "$CONTRACT_STAGING/.${pass_name}.unsorted.tmp"
  samtools index "$CONTRACT_STAGING/${pass_name}.bam" "$CONTRACT_STAGING/${pass_name}.bam.bai"
  rm -f "$CONTRACT_STAGING/.${pass_name}.unsorted.tmp"
done
printf 'controlled paired contract fixture\n' > "$CONTRACT_STAGING/bowtie2.primary.log"
printf 'controlled paired contract fixture\n' > "$CONTRACT_STAGING/bowtie2.placements.log"
python3 "$ROOT/scripts/experimental/direct_map/experimental_direct_map.py" summarize \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --sample synthetic-direct-map-paired-contract --run-id "$CONTRACT_RUN_ID" \
  --reference "$WORK/matrix/panel.fa" --index "$WORK/matrix/panel" --loci "$WORK/matrix/loci.tsv" \
  --primary-sam "$WORK/matrix/contract_paired_primary.sam" \
  --placements-sam "$WORK/matrix/contract_paired_placements.sam" \
  --primary-bam "$CONTRACT_STAGING/primary.bam" --placements-bam "$CONTRACT_STAGING/placements.bam" \
  --out-dir "$CONTRACT_STAGING" --umi-mode read_name \
  --primary-command 'controlled standard-pass MAPQ40 fixture' \
  --placements-command 'controlled placements-pass MAPQ255/MAPQ40 fixture' \
  --r1 "$WORK/matrix/contract_paired_r1.fastq" --r2 "$WORK/matrix/contract_paired_r2.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json"
python3 "$ROOT/scripts/experimental/direct_map/experimental_direct_map.py" finalize \
  --staging "$CONTRACT_STAGING" --final "$CONTRACT_FINAL" --run-id "$CONTRACT_RUN_ID" >/dev/null

FILTER_RUN_ID="direct-map-e2e-paired-mapq-filter"
FILTER_STAGING="$WORK/output/experimental/direct-map-v1/.staging/$FILTER_RUN_ID"
FILTER_FINAL="$WORK/output/experimental/direct-map-v1/runs/$FILTER_RUN_ID"
mkdir -p "$FILTER_STAGING"
for pass_name in primary placements; do
  samtools view -b -o "$FILTER_STAGING/.${pass_name}.unsorted.tmp" \
    "$WORK/matrix/contract_filter_${pass_name}.sam"
  samtools sort -o "$FILTER_STAGING/${pass_name}.bam" "$FILTER_STAGING/.${pass_name}.unsorted.tmp"
  samtools index "$FILTER_STAGING/${pass_name}.bam" "$FILTER_STAGING/${pass_name}.bam.bai"
  rm -f "$FILTER_STAGING/.${pass_name}.unsorted.tmp"
done
printf 'controlled paired filter contract fixture\n' > "$FILTER_STAGING/bowtie2.primary.log"
printf 'controlled paired filter contract fixture\n' > "$FILTER_STAGING/bowtie2.placements.log"
python3 "$ROOT/scripts/experimental/direct_map/experimental_direct_map.py" summarize \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --sample synthetic-direct-map-paired-filter --run-id "$FILTER_RUN_ID" \
  --reference "$WORK/matrix/panel.fa" --index "$WORK/matrix/panel" --loci "$WORK/matrix/contract_loci.tsv" \
  --primary-sam "$WORK/matrix/contract_filter_primary.sam" \
  --placements-sam "$WORK/matrix/contract_filter_placements.sam" \
  --primary-bam "$FILTER_STAGING/primary.bam" --placements-bam "$FILTER_STAGING/placements.bam" \
  --out-dir "$FILTER_STAGING" --umi-mode read_name \
  --primary-command 'controlled standard-pass MAPQ40/MAPQ5 fixture' \
  --placements-command 'controlled placements-pass MAPQ40/MAPQ5 fixture' \
  --r1 "$WORK/matrix/contract_filter_r1.fastq" --r2 "$WORK/matrix/contract_filter_r2.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json"
python3 "$ROOT/scripts/experimental/direct_map/experimental_direct_map.py" finalize \
  --staging "$FILTER_STAGING" --final "$FILTER_FINAL" --run-id "$FILTER_RUN_ID" >/dev/null

samtools quickcheck -v "$FINAL/primary.bam" "$FINAL/placements.bam"
samtools quickcheck -v "$REPEAT_FINAL/primary.bam" "$REPEAT_FINAL/placements.bam"
samtools quickcheck -v "$SINGLE_FINAL/primary.bam" "$SINGLE_FINAL/placements.bam"
samtools quickcheck -v "$CONTRACT_FINAL/primary.bam" "$CONTRACT_FINAL/placements.bam"
samtools quickcheck -v "$FILTER_FINAL/primary.bam" "$FILTER_FINAL/placements.bam"
for deterministic_artifact in direct_map_metrics.json coverage_metrics.tsv read_classifications.tsv template_geometry.tsv; do
  cmp "$FINAL/$deterministic_artifact" "$REPEAT_FINAL/$deterministic_artifact"
done
cmp <(samtools view "$FINAL/primary.bam") <(samtools view "$REPEAT_FINAL/primary.bam")
cmp <(samtools view "$FINAL/placements.bam") <(samtools view "$REPEAT_FINAL/placements.bam")
SECONDARY_COUNT="$(samtools view -c -f 256 "$FINAL/placements.bam")"
[[ "$SECONDARY_COUNT" -gt 0 ]] || {
  echo "-a placements BAM did not preserve secondary alignments" >&2
  exit 1
}

python3 - "$FINAL" "$SINGLE_FINAL" "$CONTRACT_FINAL" "$WORK/matrix/contract_paired_expected.json" \
  "$FILTER_FINAL" "$WORK/matrix/contract_filter_expected.json" "$ROOT" <<'PY'
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
single_root = Path(sys.argv[2])
contract_root = Path(sys.argv[3])
contract_expected = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
filter_root = Path(sys.argv[5])
filter_expected = json.loads(Path(sys.argv[6]).read_text(encoding="utf-8"))
repo_root = Path(sys.argv[7])
sys.path.insert(0, str(repo_root))
from scripts.evidence.common import validate_artifact_manifest
with (root / "SUCCESS.json").open(encoding="utf-8") as handle:
    success = json.load(handle)
with (root / "artifact_manifest.json").open(encoding="utf-8") as handle:
    manifest = json.load(handle)
with (root / "direct_map_metrics.json").open(encoding="utf-8") as handle:
    metrics = json.load(handle)
with (root / "provenance.json").open(encoding="utf-8") as handle:
    provenance = json.load(handle)
with (root / "profile.json").open(encoding="utf-8") as handle:
    profile = json.load(handle)
with (root / "panel_manifest.json").open(encoding="utf-8") as handle:
    panel_manifest = json.load(handle)
with (root / "coverage_metrics.tsv").open(encoding="utf-8", newline="") as handle:
    coverage = list(csv.DictReader(handle, delimiter="\t"))

if success["governance_state"] != "EXPERIMENTAL" or success["diagnostic"] is not False:
    raise SystemExit("SUCCESS governance is not experimental/non-diagnostic")
contracts = {
    "metrics": "experimental-direct-map-metrics-v2",
    "invariants": "experimental-direct-map-invariants-v2",
    "coverage_tsv": "experimental-direct-map-coverage-v2",
}
if profile["schema_version"] != "experimental-direct-map-profile-v2" or profile["output_contracts"] != contracts:
    raise SystemExit("retained profile does not declare the v2 output contracts")
if metrics["schema_version"] != contracts["metrics"] or metrics["contract_versions"] != contracts:
    raise SystemExit("metrics schema/contract identity is incompatible")
if metrics["invariants"]["schema_version"] != contracts["invariants"]:
    raise SystemExit("invariants schema identity is incompatible")
if provenance["contract_versions"] != contracts:
    raise SystemExit("provenance does not cross-identify output contracts")
if provenance["schema_version"] != "experimental-direct-map-provenance-v2":
    raise SystemExit("provenance does not identify the v2 provenance schema")
if provenance["governance_state"] != "EXPERIMENTAL" or provenance["diagnostic"] is not False:
    raise SystemExit("provenance governance is not experimental/non-diagnostic")
# The persisted manifest must satisfy the shared closed schema, reloaded from disk --
# validating an in-memory dict that is then modified before writing proved nothing.
if set(manifest) != {"schema_version", "files"}:
    raise SystemExit(f"persisted manifest is not the shared closed schema: {sorted(manifest)}")
reloaded_errors = validate_artifact_manifest(root, manifest)
if reloaded_errors:
    raise SystemExit(f"persisted artifact manifest reloaded from disk is invalid: {reloaded_errors}")
if success["schema_version"] != "experimental-direct-map-success-v2" or success["contract_versions"] != contracts:
    raise SystemExit("SUCCESS does not cross-identify output contracts")
if {row["schema_version"] for row in coverage} != {contracts["coverage_tsv"]}:
    raise SystemExit("coverage TSV rows do not identify the v2 contract")
if success["artifact_count"] != len(manifest["files"]):
    raise SystemExit("SUCCESS artifact count differs from manifest")
manifest_hash = hashlib.sha256((root / "artifact_manifest.json").read_bytes()).hexdigest()
if manifest_hash != success["artifact_manifest_sha256"]:
    raise SystemExit("SUCCESS manifest hash mismatch")
for relative, expected in manifest["files"].items():
    path = root / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise SystemExit(f"manifest mismatch for {relative}")
latest_payload_mtime = max((root / relative).stat().st_mtime_ns for relative in manifest["files"])
if (root / "SUCCESS.json").stat().st_mtime_ns < latest_payload_mtime:
    raise SystemExit("SUCCESS.json was not written after payload artifacts")

counts = metrics["read_classification_counts"]
if sum(counts.values()) != metrics["input_reads"]:
    raise SystemExit("read categories do not sum to FASTQ denominator")
if counts["EQUIVALENT_AMBIGUOUS"] < 1 or counts["MULTI_UNEQUAL"] < 1 or counts["UNMAPPED"] < 1:
    raise SystemExit(f"synthetic matrix did not exercise expected classes: {counts}")
if metrics["orthogonal_counts"]["secondary"] < 1:
    raise SystemExit("secondary alignments were not counted")
if metrics["orthogonal_counts"]["mapq_unknown"] < 1:
    raise SystemExit("unknown placement MAPQ was not counted explicitly")
if metrics["orthogonal_count_source"] != "PLACEMENTS_PASS":
    raise SystemExit("orthogonal counters do not declare the contractual placements-pass source")
if metrics["profile_id"] != "GENEIN-EV2-DIRECT-MAP-001.profile-v1.2" or metrics["profile_revision"] != "1.2":
    raise SystemExit("metrics do not identify the amended v1.2 profile")
if metrics["pipeline_version"] != "experimental-direct-map-1.2":
    raise SystemExit("metrics do not identify pipeline version 1.2")
if provenance["profile_id"] != metrics["profile_id"] or provenance["pipeline_version"] != metrics["pipeline_version"]:
    raise SystemExit("metrics/provenance profile and pipeline identities differ")
if profile["profile_id"] != metrics["profile_id"] or profile["profile_compatibility"]["semantic_compatibility"] != "INCOMPATIBLE_MAPQ255_MEASUREMENT":
    raise SystemExit("retained profile does not expose the v1.1 to v1.2 semantic boundary")
if success["pipeline_version"] != metrics["pipeline_version"]:
    raise SystemExit("SUCCESS does not identify the same v1.2 pipeline")
if metrics["coverage_measurement"]["unknown_mapq_count_scope"] != "PER_CELL_AFTER_STAGE_REGION_AND_BASEQ_FILTERS":
    raise SystemExit("unknown MAPQ counts do not declare their per-cell filtered scope")
if any(record["role"] in {"CONTROL", "LOW_COMPLEXITY_CONTROL"} for record in panel_manifest["references"]):
    raise SystemExit("controls NOT_APPLICABLE conflicts with a control-role panel reference")
if metrics["stage_states"]["POST_UMI"]["state"] != "MEASURED":
    raise SystemExit("declared read-name UMI ablation was not measured")
if metrics["stage_states"]["POST_COORDINATE_EXCLUSION"]["retained_templates"] >= metrics["input_templates"]:
    raise SystemExit("coordinate duplicate ablation did not exclude the synthetic duplicates")
geometries = {row["geometry"]: row["templates"] for row in metrics["template_geometry"]}
for required_geometry in ("proper", "discordant", "orphan", "unmapped_pair"):
    if geometries.get(required_geometry, 0) < 1:
        raise SystemExit(f"paired geometry was not exercised: {required_geometry} => {geometries}")
if len(provenance["bowtie2_index"]) != 6:
    raise SystemExit("all six Bowtie2 index components were not hashed")
if "2.5.5" not in provenance["tools"]["bowtie2"]["version"]:
    raise SystemExit("Bowtie2 locked version was not recorded")
if "1.24" not in provenance["tools"]["samtools"]["version"]:
    raise SystemExit("Samtools locked version was not recorded")
retained = provenance.get("retained_artifacts", {})
if {retained.get(name, {}).get("path") for name in ("primary_bam", "placements_bam")} != {"primary.bam", "placements.bam"}:
    raise SystemExit("retained BAM provenance is incomplete")
if "primary_sam" in provenance.get("external_inputs", {}) or "placements_sam" in provenance.get("external_inputs", {}):
    raise SystemExit("deleted temporary SAM was recorded as a retained/verifiable input")
if provenance.get("intermediates", {}).get("primary_sam") != {"retained": False, "represented_by": "primary.bam"}:
    raise SystemExit("non-retained primary SAM is not represented explicitly")
# The frozen Gene-In 1.1 baseline is absent from this history, so the historical
# comparison cannot run. It must be declared NOT_EXECUTED -- never quietly dropped and
# never reported as a pass -- and the run must instead prove its own integrity chain.
baseline = provenance["baseline_comparison"]
if baseline["state"] != "NOT_EXECUTED" or baseline["comparison"] != "FROZEN_PUBLIC_ARTIFACTS":
    raise SystemExit(f"baseline comparison does not declare its state: {baseline}")
if "all_unchanged" in baseline or "PASS" in json.dumps(baseline):
    raise SystemExit("baseline comparison must not claim a pass it did not perform")
if not baseline.get("reason") or not baseline.get("guarantee_not_provided"):
    raise SystemExit("baseline comparison does not state why it did not run or what it cannot guarantee")
source = provenance["source_state"]
if not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
    raise SystemExit("provenance does not record a resolvable executing commit")
if source["working_tree"] not in {"CLEAN", "MODIFIED"}:
    raise SystemExit("provenance does not record whether the executing tree was modified")
if source["commit_identifies_executed_source"] is not (source["working_tree"] == "CLEAN"):
    raise SystemExit("source state contradicts itself about whether HEAD identifies the executed source")
module_sources = source["executing_module_sources"]
if not any(name.endswith("experimental_direct_map.py") for name in module_sources):
    raise SystemExit("provenance does not hash the executing direct-map module source")
for relative, entry in module_sources.items():
    if hashlib.sha256((repo_root / relative).read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit(f"executing module source hash does not match the file on disk: {relative}")
if provenance["parameters"]["track_semantics"]["all_eligible_mapq_source"] != "PLACEMENT":
    raise SystemExit("provenance does not retain the approved placement-MAPQ semantics")
if not coverage or {row["scope"] for row in coverage} != {"REFERENCE", "LOCUS"}:
    raise SystemExit("reference/locus coverage grid is incomplete")
if {row["track"] for row in coverage} != {"unique", "all_eligible"}:
    raise SystemExit("unique/all_eligible coverage tracks are incomplete")
if {int(row["window_bp"]) for row in coverage} != {20, 50, 100}:
    raise SystemExit("window grid is incomplete")
if {int(row["minimum_mapq"]) for row in coverage} != {0, 10, 20, 30}:
    raise SystemExit("MAPQ grid is incomplete")
if {int(row["minimum_base_quality"]) for row in coverage} != {0, 20, 30}:
    raise SystemExit("baseQ grid is incomplete")
if {row["unit"] for row in coverage} != {"READ", "TEMPLATE"}:
    raise SystemExit("read/template depth grid is incomplete")
if {row["stage"] for row in coverage} != {"PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI"}:
    raise SystemExit("dedup/UMI ablation grid is incomplete")
unique_states = {row["measurement_state"] for row in coverage if row["track"] == "unique"}
all_eligible_states = {row["measurement_state"] for row in coverage if row["track"] == "all_eligible"}
if unique_states != {"MEASURED"}:
    raise SystemExit(f"default-pass unique coverage was not measured: {unique_states}")
if all_eligible_states != {"MEASURED", "NOT_MEASURED"}:
    raise SystemExit(f"all_eligible did not separate MAPQ 0 from positive thresholds: {all_eligible_states}")
all_mapq0_read = [
    row for row in coverage
    if row["track"] == "all_eligible" and int(row["minimum_mapq"]) == 0 and row["unit"] == "READ"
]
if not all_mapq0_read or {row["measurement_state"] for row in all_mapq0_read} != {"MEASURED"}:
    raise SystemExit("all_eligible READ coverage at MAPQ 0 was not measured")
all_positive = [
    row for row in coverage
    if row["track"] == "all_eligible" and int(row["minimum_mapq"]) > 0
]
affected_positive = [row for row in all_positive if int(row["unknown_mapq_count"] or 0) > 0]
unaffected_positive_read = [
    row for row in all_positive
    if int(row["unknown_mapq_count"] or 0) == 0 and row["unit"] == "READ"
]
if not affected_positive or {row["measurement_state"] for row in affected_positive} != {"NOT_MEASURED"}:
    raise SystemExit("affected positive-MAPQ all_eligible cells were not NOT_MEASURED")
if not unaffected_positive_read or {row["measurement_state"] for row in unaffected_positive_read} != {"MEASURED"}:
    raise SystemExit("positive-MAPQ cells without an eligible unknown placement were not measured")
if any(row["depth_total"] or "unknown (255)" not in row["reason"] for row in affected_positive):
    raise SystemExit("affected positive-MAPQ TSV cells lack null values or an auditable MAPQ-255 reason")
if any(
    "PNEXT" in row["reason"] or "unknown (255)" not in row["reason"]
    for row in affected_positive if row["unit"] == "TEMPLATE"
):
    raise SystemExit("template pairing masked the MAPQ-255 reason in an affected positive-threshold cell")
positive_structured = [
    item for item in metrics["coverage"]
    if item["track"] == "all_eligible" and int(item["minimum_mapq"]) > 0 and
    int(item["unknown_mapq_count"] or 0) > 0
]
if any(
    item["metrics"]["depth_total"]["state"] != "NOT_MEASURED" or
    item["metrics"]["depth_total"]["value"] is not None or
    item["metrics"]["denominator_bp"]["state"] != "MEASURED"
    for item in positive_structured
):
    raise SystemExit("structured positive-MAPQ cells do not preserve null metrics and measured denominators")
unique_mapq0 = {
    tuple(row[field] for field in (
        "scope", "reference_id", "region_id", "minimum_base_quality", "unit", "stage", "window_bp",
    )): int(row["depth_total"])
    for row in coverage
    if row["track"] == "unique" and int(row["minimum_mapq"]) == 0 and row["measurement_state"] == "MEASURED"
}
if not any(
    int(row["depth_total"]) > unique_mapq0.get(tuple(row[field] for field in (
        "scope", "reference_id", "region_id", "minimum_base_quality", "unit", "stage", "window_bp",
    )), int(row["depth_total"]))
    for row in all_mapq0_read
):
    raise SystemExit("secondary placements did not add MAPQ-0 all_eligible depth beyond unique")
all_aggregate = metrics["coverage_measurement"]["by_track"]["all_eligible"]
if all_aggregate["state"] != "MEASURED" or all_aggregate["completeness"] != "PARTIAL":
    raise SystemExit("all_eligible aggregate does not distinguish partial measurement from no measurement")
if not 0 < all_aggregate["measured_cell_fraction"] < 1:
    raise SystemExit("all_eligible aggregate lacks an honest measured-cell fraction")
cross_track = metrics["invariants"]["cross_track_unique_le_all_eligible"]
if cross_track["state"] != "MEASURED" or cross_track["evaluated_checks"] < 1:
    raise SystemExit("cross-track unique<=all_eligible was not evaluated at MAPQ 0")
if cross_track["positive_thresholds"]["state"] != "NOT_APPLICABLE" or not cross_track["positive_thresholds"]["reason"]:
    raise SystemExit("positive-threshold cross-track comparison lacks an auditable NOT_APPLICABLE state")
if metrics["invariants"]["state"] != "MEASURED" or metrics["invariants"]["coverage_cells_measured"] == 0:
    raise SystemExit("invariants.state does not reflect the coverage cells actually evaluated")
limitations = " ".join(metrics["limitations"])
if "partial reconciliation is not implemented" not in limitations or "partial template measurement is not implemented" not in limitations:
    raise SystemExit("global NOT_MEASURED limitations are not explicit")
if not any(item["metrics"]["cv_depth_complete"]["state"] == "UNDEFINED" for item in metrics["coverage"]):
    raise SystemExit("zero-depth undefined state was not preserved")

with (single_root / "direct_map_metrics.json").open(encoding="utf-8") as handle:
    single_metrics = json.load(handle)
with (single_root / "coverage_metrics.tsv").open(encoding="utf-8", newline="") as handle:
    single_coverage = list(csv.DictReader(handle, delimiter="\t"))
if single_metrics["template_geometry"] != [{
    "geometry": "single_end", "measurement_state": "MEASURED", "reads": 3,
    "sample_id": "synthetic-direct-map-single", "templates": 3,
}]:
    raise SystemExit(f"single-end geometry is incomplete: {single_metrics['template_geometry']}")
if single_metrics["stage_states"]["POST_UMI"]["state"] != "NOT_APPLICABLE":
    raise SystemExit("undeclared UMI did not produce NOT_APPLICABLE")
if single_metrics["stage_states"]["POST_UMI"]["retained_templates"] is not None:
    raise SystemExit("NOT_APPLICABLE UMI stage emitted a numeric retained_templates value")
post_umi_states = {row["measurement_state"] for row in single_coverage if row["stage"] == "POST_UMI"}
if post_umi_states != {"NOT_APPLICABLE"}:
    raise SystemExit(f"POST_UMI cells have unexpected states: {post_umi_states}")
single_mapq0_template = [
    row for row in single_coverage
    if row["track"] == "all_eligible" and int(row["minimum_mapq"]) == 0 and
    row["unit"] == "TEMPLATE" and row["stage"] != "POST_UMI"
]
if not single_mapq0_template or {row["measurement_state"] for row in single_mapq0_template} != {"MEASURED"}:
    raise SystemExit("all_eligible TEMPLATE coverage at MAPQ 0 was not measured when pairing was not applicable")
single_affected_positive_template = [
    row for row in single_coverage
    if row["track"] == "all_eligible" and int(row["minimum_mapq"]) > 0 and
    row["unit"] == "TEMPLATE" and row["stage"] != "POST_UMI" and int(row["unknown_mapq_count"] or 0) > 0
]
if not single_affected_positive_template or any(
    row["measurement_state"] != "NOT_MEASURED" or row["depth_total"] or "unknown (255)" not in row["reason"]
    for row in single_affected_positive_template
):
    raise SystemExit("all_eligible TEMPLATE positive-threshold cells do not preserve MAPQ-255 uncertainty")

with (contract_root / "coverage_metrics.tsv").open(encoding="utf-8", newline="") as handle:
    contract_coverage = list(csv.DictReader(handle, delimiter="\t"))
contract_mapq0 = [
    row for row in contract_coverage
    if row["scope"] == "REFERENCE" and row["reference_id"] == "unique_ref" and
    row["track"] == "all_eligible" and int(row["minimum_mapq"]) == 0 and
    int(row["minimum_base_quality"]) == 0 and row["unit"] == "TEMPLATE" and
    row["stage"] == "PRE_DEDUP" and int(row["window_bp"]) == 20
]
contract_positive = [
    row for row in contract_coverage
    if row["scope"] == "REFERENCE" and row["reference_id"] == "unique_ref" and
    row["track"] == "all_eligible" and int(row["minimum_mapq"]) > 0 and
    int(row["minimum_base_quality"]) == 0 and row["unit"] == "TEMPLATE" and
    row["stage"] == "PRE_DEDUP" and int(row["window_bp"]) == 20
]
if len(contract_mapq0) != 1 or contract_mapq0[0]["measurement_state"] != contract_expected["all_eligible_mapq0_template_state"]:
    raise SystemExit("paired MAPQ255/MAPQ40 all_eligible TEMPLATE cell was not measured at MAPQ 0")
if int(contract_mapq0[0]["pairing_invalid_pnext_count"]) != contract_expected["pairing_invalid_pnext_count"]:
    raise SystemExit("reciprocal MAPQ255/MAPQ40 pair was mislabeled as invalid PNEXT")
if len(contract_positive) != 3 or any(
    row["measurement_state"] != contract_expected["all_eligible_positive_template_state"] or
    row["depth_total"] or contract_expected["all_eligible_positive_reason_contains"] not in row["reason"]
    for row in contract_positive
):
    raise SystemExit("paired MAPQ255/MAPQ40 positive-threshold cells did not preserve MAPQ uncertainty")

with (filter_root / "coverage_metrics.tsv").open(encoding="utf-8", newline="") as handle:
    filter_coverage = list(csv.DictReader(handle, delimiter="\t"))
filter_ref = [
    row for row in filter_coverage
    if row["scope"] == "REFERENCE" and row["reference_id"] == "unique_ref" and
    row["track"] == "all_eligible" and int(row["minimum_mapq"]) == 20 and
    int(row["minimum_base_quality"]) == 0 and row["unit"] == "TEMPLATE" and
    row["stage"] == "PRE_DEDUP" and int(row["window_bp"]) == 20
]
filter_locus_b = [
    row for row in filter_coverage
    if row["scope"] == "LOCUS" and row["region_id"] == "contract_locus_b" and
    row["track"] == "all_eligible" and int(row["minimum_mapq"]) == 20 and
    int(row["minimum_base_quality"]) == 0 and row["unit"] == "TEMPLATE" and
    row["stage"] == "PRE_DEDUP" and int(row["window_bp"]) == 20
]
if len(filter_ref) != 1 or filter_ref[0]["measurement_state"] != filter_expected["all_eligible_mapq20_template_state"]:
    raise SystemExit("MAPQ40/MAPQ5 same-region TEMPLATE cell was not measured at MAPQ 20")
if int(filter_ref[0]["pairing_invalid_pnext_count"]) != filter_expected["pairing_invalid_pnext_count"]:
    raise SystemExit("MAPQ-filtered reciprocal mate was mislabeled as invalid PNEXT")
if int(filter_ref[0]["pairing_filtered_mate_count"]) != filter_expected["ref_region_filtered_mate_count"]:
    raise SystemExit("MAPQ-filtered mate was not counted in the same-region cell")
if json.loads(filter_ref[0]["pairing_filtered_mate_reasons_json"]) != filter_expected["ref_region_filtered_mate_reasons"]:
    raise SystemExit("MAPQ-filtered mate reason is not auditable")
if len(filter_locus_b) != 1 or filter_locus_b[0]["measurement_state"] != filter_expected["locus_b_template_state"]:
    raise SystemExit("single-mate locus cell was not measured")
if int(filter_locus_b[0]["pairing_filtered_mate_count"]) != filter_expected["locus_b_filtered_mate_count"]:
    raise SystemExit("out-of-region mate was not counted in the single-mate locus cell")
if json.loads(filter_locus_b[0]["pairing_filtered_mate_reasons_json"]) != filter_expected["locus_b_filtered_mate_reasons"]:
    raise SystemExit("out-of-region mate reason is not auditable")
with (filter_root / "direct_map_metrics.json").open(encoding="utf-8") as handle:
    filter_metrics = json.load(handle)
pairing_summary = filter_metrics["coverage_measurement"]["template_pairing"]
if pairing_summary["template_cell_count"] < 2 or pairing_summary["filtered_mate_count"] < 2:
    raise SystemExit("coverage-level template_pairing aggregate did not sum per-cell filtered mates")
if not pairing_summary["filtered_mate_reasons"].get("MAPQ") or not pairing_summary["filtered_mate_reasons"].get("REGION"):
    raise SystemExit("template_pairing aggregate does not preserve auditable MAPQ/REGION reasons")
if filter_metrics["coverage_measurement"]["template_pairing_scope"] != "ALL_TEMPLATE_CELLS_PER_STAGE_TRACK_MAPQ_BASEQ_REGION_AFTER_FILTERS":
    raise SystemExit("template_pairing scope is not auditable")
print("PASS: real locked-tool experimental direct-map E2E")
PY

SUCCESS_HASH_BEFORE="$(sha256sum "$FINAL/SUCCESS.json" | awk '{print $1}')"
printf 'locus_id\tsseqid\treference_intervals\ninvalid_locus\tmissing_reference\t1-10\n' > "$WORK/matrix/invalid_loci.tsv"
if bash "$ROOT/scripts/experimental/direct_map/run.sh" \
  --sample synthetic-direct-map-failure \
  --run-id direct-map-e2e-failure \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --reference "$WORK/matrix/panel.fa" \
  --index "$WORK/matrix/panel" \
  --loci "$WORK/matrix/invalid_loci.tsv" \
  --single "$WORK/matrix/single.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json" \
  --umi-mode none \
  --out-root "$WORK/output" \
  --threads 1 >"$WORK/expected-failure.stdout" 2>"$WORK/expected-failure.stderr"; then
  echo "invalid loci unexpectedly produced a successful experimental run" >&2
  exit 1
fi
grep -q "locus references unknown sequence: missing_reference" "$WORK/expected-failure.stderr" || {
  echo "transactional failure test did not reach invalid-locus validation" >&2
  exit 1
}
[[ ! -e "$WORK/output/experimental/direct-map-v1/runs/direct-map-e2e-failure" ]] || {
  echo "failed experimental run replaced/promoted a final directory" >&2
  exit 1
}
[[ ! -e "$WORK/output/experimental/direct-map-v1/.staging/direct-map-e2e-failure" ]] || {
  echo "failed experimental run left reusable staging" >&2
  exit 1
}
SUCCESS_HASH_AFTER="$(sha256sum "$FINAL/SUCCESS.json" | awk '{print $1}')"
[[ "$SUCCESS_HASH_BEFORE" == "$SUCCESS_HASH_AFTER" ]] || {
  echo "failed run changed the last valid SUCCESS.json" >&2
  exit 1
}

DIVERGENT_RUN_ID="direct-map-e2e-divergent-reference"
if bash "$ROOT/scripts/experimental/direct_map/run.sh" \
  --sample synthetic-direct-map-divergent-reference \
  --run-id "$DIVERGENT_RUN_ID" \
  --profile "$ROOT/config/experimental/direct_map_v1.json" \
  --reference "$WORK/matrix/panel.fa" \
  --index "$WORK/matrix/divergent-index" \
  --loci "$WORK/matrix/loci.tsv" \
  --single "$WORK/matrix/single.fastq" \
  --panel-manifest "$WORK/matrix/panel_manifest.json" \
  --umi-mode none --out-root "$WORK/output" --threads 1 \
  >"$WORK/divergent-run.stdout" 2>"$WORK/divergent-run.stderr"; then
  echo "index/declared-FASTA divergence unexpectedly produced a successful run" >&2
  exit 1
fi
grep -q "mapped alignment references sequence absent from declared FASTA:.*ref_ghost" "$WORK/divergent-run.stderr" || {
  echo "divergent-reference failure did not identify ref_ghost" >&2
  exit 1
}
[[ ! -e "$WORK/output/experimental/direct-map-v1/runs/$DIVERGENT_RUN_ID" ]] || {
  echo "divergent-reference run promoted a final directory" >&2
  exit 1
}
[[ ! -e "$WORK/output/experimental/direct-map-v1/.staging/$DIVERGENT_RUN_ID" ]] || {
  echo "divergent-reference run left reusable staging" >&2
  exit 1
}
SUCCESS_HASH_DIVERGENT_AFTER="$(sha256sum "$FINAL/SUCCESS.json" | awk '{print $1}')"
[[ "$SUCCESS_HASH_BEFORE" == "$SUCCESS_HASH_DIVERGENT_AFTER" ]] || {
  echo "divergent-reference run changed the last valid SUCCESS.json" >&2
  exit 1
}
