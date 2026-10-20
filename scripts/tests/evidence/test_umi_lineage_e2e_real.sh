#!/usr/bin/env bash
# E2E UMI real (read_name + tag + none) for GI-EG002 — pinned Gene-In tools.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_BIN="${GENE_IN_ENV_BIN:-${GENEIN_BUNDLE_DIR:-$HOME/.gene-in-bundle}/env/bin}"
export PATH="$ENV_BIN:/usr/bin:/bin"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

for cmd in python3 blastn bowtie2 bowtie2-build samtools umi_tools makeblastdb; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "SKIP: missing $cmd"; exit 77; }
done

LOG_ROOT="${1:-$ROOT/logs/etapa3/gi-eg002-mapper-v0.2.2/umi-e2e}"
mkdir -p "$LOG_ROOT"
mkdir -p "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}"
WORK="$(mktemp -d "${GENEIN_TEST_ARTIFACT_ROOT:-/tmp}/genein-gi-eg002-umi.XXXXXX")"
echo "UMI_WORK=$WORK"
echo "UMI_LOG=$LOG_ROOT"

require_empty_log_slot() {
  local run_id="$1"
  if [[ -e "$LOG_ROOT/$run_id" ]]; then
    echo "[FATAL] persistent E2E destination already exists: $LOG_ROOT/$run_id" >&2
    exit 2
  fi
}

python3 - "$WORK" <<'PY'
from pathlib import Path
import sys

work = Path(sys.argv[1])
query = "ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGTGCATG"
comp = str.maketrans("ACGT", "TGCA")

def revcomp(seq: str) -> str:
    return seq.translate(comp)[::-1]

# Contig/query and panel reference share the same core sequence.
(work / "query.fa").write_text(f">query_umi\n{query}\n", encoding="utf-8")
(work / "panel.fa").write_text(f">target_ref\n{query}TGCATCGATCGT\n", encoding="utf-8")
(work / "labels.tsv").write_text(
    "sseqid\tcategory\ttaxon\tsegment\n"
    "target_ref\tTARGET_VIRUS\tsynthetic_target\tunsegmented\n",
    encoding="utf-8",
)

# Proper FR pairs that both map: R1 = forward window, R2 = reverse-complement of same window.
umi = "ACGTAC"
r1_seq = query[0:50]
r2_seq = revcomp(r1_seq)
qual = "I" * 50
r1_lines = []
r2_lines = []
for idx, start in enumerate((0, 5), start=1):
    left = query[start:start + 50]
    right = revcomp(left)
    # Identical QNAME base for both mates; UMI after underscore for read_id extraction.
    name = f"read{idx}_{umi}"
    r1_lines.extend([f"@{name}", left, "+", "I" * len(left)])
    r2_lines.extend([f"@{name}", right, "+", "I" * len(right)])
(work / "r1.fastq").write_text("\n".join(r1_lines) + "\n", encoding="utf-8")
(work / "r2.fastq").write_text("\n".join(r2_lines) + "\n", encoding="utf-8")
PY

cp "$WORK/panel.fa" "$WORK/panel_ref.fa"
makeblastdb -in "$WORK/panel.fa" -dbtype nucl -parse_seqids -out "$WORK/panel" >/dev/null
python3 "$ROOT/scripts/tests/write_blast_fixture_manifest.py" "$WORK/panel"
bowtie2-build "$WORK/panel_ref.fa" "$WORK/panel_idx" >/dev/null 2>&1

run_mode() {
  local mode="$1"
  local run_id="$2"
  local r1="$3"
  local r2="$4"
  require_empty_log_slot "$run_id"
  bash "$ROOT/scripts/evidence/run.sh" \
    --sample umi_synth \
    --queries "$WORK/query.fa" \
    --profiles "$ROOT/config/evidence_profiles.json" \
    --evidence-root "$WORK/evidence_$mode" \
    --run-id "$run_id" \
    --composite-db "$WORK/panel" \
    --subject-labels "$WORK/labels.tsv" \
    --panel-index "$WORK/panel_idx" \
    --panel-fasta "$WORK/panel_ref.fa" \
    --r1 "$r1" \
    --r2 "$r2" \
    --library-mode shotgun \
    --umi-mode "$mode" \
    --threads 1 \
    --assembly-method velvet >/dev/null
  local final="$WORK/evidence_$mode/runs/$run_id"
  python3 - "$final" "$mode" <<'PY'
import csv, json, sys
from pathlib import Path
root = Path(sys.argv[1]); mode = sys.argv[2]
success = json.loads((root/"SUCCESS.json").read_text(encoding="utf-8"))
assert success.get("mapper_source_version") == "0.2.2"
rows = list(csv.DictReader((root/"template_lineage.tsv").open(encoding="utf-8", newline=""), delimiter="\t"))
assert rows, f"{mode}: expected lineage rows"
if mode == "none":
    assert all(r["eligible"] == "false" for r in rows)
    assert all(r["lineage_id"] == "" for r in rows)
    assert all(r["rejection_reason"] == "MISSING_FIELD" for r in rows)
    assert any(int(r["read_count"]) > 0 for r in rows)
    assert any(int(r["template_count"]) >= 1 for r in rows)
else:
    eligible = [r for r in rows if r["eligible"] == "true"]
    assert eligible, f"{mode}: expected eligible lineages"
    assert all(r["lineage_id"] for r in eligible)
    assert all(int(r["template_count"]) >= 1 for r in eligible)
    assert all(int(r["read_count"]) >= 1 for r in eligible)
    # Counts, not booleans:
    assert all(str(r["proper_pair_templates"]).isdigit() for r in eligible)
    assert all(str(r["discordant_templates"]).isdigit() for r in eligible)
print(f"PASS umi_mode={mode} lineages={len(rows)} eligible={sum(1 for r in rows if r['eligible']=='true')}")
PY
  cp -a "$final" "$LOG_ROOT/$run_id"
}

run_mode read_name umi-readname-run1 "$WORK/r1.fastq" "$WORK/r2.fastq"
run_mode read_name umi-readname-run2 "$WORK/r1.fastq" "$WORK/r2.fastq"
python3 - "$LOG_ROOT/umi-readname-run1/template_lineage.tsv" "$LOG_ROOT/umi-readname-run2/template_lineage.tsv" <<'PY'
from pathlib import Path
import csv, sys
a = list(csv.DictReader(Path(sys.argv[1]).open(encoding="utf-8", newline=""), delimiter="\t"))
b = list(csv.DictReader(Path(sys.argv[2]).open(encoding="utf-8", newline=""), delimiter="\t"))
assert len(a) == len(b) and len(a) > 0
# Same seed → same final_umi / template_count / mapped_bases structure
for left, right in zip(a, b):
    for key in ("final_umi", "template_count", "read_count", "mapped_bases", "eligible"):
        assert left[key] == right[key], (key, left[key], right[key])
print("PASS read_name repeatability", len(a))
PY

# tag mode: build coordinate BAM, annotate RX, group with --extract-umi-method=tag
require_empty_log_slot umi-tag-run1
python3 - "$WORK" <<'PY'
from pathlib import Path
import sys
work = Path(sys.argv[1])
query = "ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGTGCATG"
comp = str.maketrans("ACGT", "TGCA")
umi = "ACGTAC"

def revcomp(seq: str) -> str:
    return seq.translate(comp)[::-1]

r1, r2 = [], []
for idx, start in enumerate((0, 5), start=1):
    bio = query[start:start + 50]
    name = f"tagread{idx}"
    left, right = bio, revcomp(bio)
    r1.extend([f"@{name}", left, "+", "I" * len(left)])
    r2.extend([f"@{name}", right, "+", "I" * len(right)])
(work / "tag_plain_r1.fastq").write_text("\n".join(r1) + "\n", encoding="utf-8")
(work / "tag_plain_r2.fastq").write_text("\n".join(r2) + "\n", encoding="utf-8")
(work / "tag_umi.txt").write_text(umi + "\n", encoding="utf-8")
PY

TAG_DIR="$WORK/tag_map"
mkdir -p "$TAG_DIR"
bowtie2 --very-sensitive-local -x "$WORK/panel_idx" \
  -1 "$WORK/tag_plain_r1.fastq" -2 "$WORK/tag_plain_r2.fastq" -p 1 \
  -S "$TAG_DIR/raw.sam" 2> "$TAG_DIR/bowtie2.log"
samtools view -b -F 2304 -q 10 "$TAG_DIR/raw.sam" | samtools sort -n -o "$TAG_DIR/name.bam"
samtools fixmate -m "$TAG_DIR/name.bam" "$TAG_DIR/fixmate.bam"
samtools sort -o "$TAG_DIR/coordinate.bam" "$TAG_DIR/fixmate.bam"
python3 - "$TAG_DIR/coordinate.bam" "$WORK/tag_umi.txt" "$TAG_DIR/rx.bam" <<'PY'
import sys
import pysam
in_bam, umi_path, out_bam = sys.argv[1:4]
umi = open(umi_path, encoding="utf-8").read().strip()
with pysam.AlignmentFile(in_bam, "rb") as src:
    with pysam.AlignmentFile(out_bam, "wb", template=src) as dst:
        for read in src:
            read.set_tag("RX", umi, value_type="Z")
            dst.write(read)
PY
samtools index "$TAG_DIR/rx.bam"
umi_tools group --method=directional --edit-distance-threshold=1 --random-seed=1 --paired \
  --extract-umi-method=tag --umi-tag=RX --output-bam \
  --stdin "$TAG_DIR/rx.bam" --stdout "$TAG_DIR/grouped.bam" --log="$TAG_DIR/group.log"
samtools view -h "$TAG_DIR/grouped.bam" > "$TAG_DIR/lineage.sam"
# Loci from a prior Evidence V2 none/read_name run panel
bash "$ROOT/scripts/evidence/run.sh" \
  --sample umi_synth \
  --queries "$WORK/query.fa" \
  --profiles "$ROOT/config/evidence_profiles.json" \
  --evidence-root "$WORK/evidence_tag_loci" \
  --run-id umi-tag-loci \
  --composite-db "$WORK/panel" \
  --subject-labels "$WORK/labels.tsv" \
  --threads 1 \
  --assembly-method velvet >/dev/null
LOCI="$WORK/evidence_tag_loci/runs/umi-tag-loci/locus_evidence.tsv"
python3 "$ROOT/scripts/evidence/build_template_lineage.py" \
  --sam "$TAG_DIR/lineage.sam" \
  --loci "$LOCI" \
  --out "$TAG_DIR/template_lineage.tsv" \
  --run-id umi-tag-run1 \
  --sample umi_synth \
  --library-mode shotgun \
  --umi-mode tag
python3 - "$TAG_DIR/template_lineage.tsv" <<'PY'
import csv, sys
from pathlib import Path
rows = list(csv.DictReader(Path(sys.argv[1]).open(encoding="utf-8", newline=""), delimiter="\t"))
assert rows, "tag: expected lineage rows"
eligible = [r for r in rows if r["eligible"] == "true"]
assert eligible, "tag: expected eligible lineages"
assert all(r["lineage_id"] for r in eligible)
assert all(int(r["template_count"]) >= 1 for r in eligible)
print(f"PASS umi_mode=tag lineages={len(rows)} eligible={len(eligible)}")
PY
mkdir -p "$LOG_ROOT/umi-tag-run1"
cp -a "$TAG_DIR/template_lineage.tsv" "$LOG_ROOT/umi-tag-run1/"
cp -a "$TAG_DIR/group.log" "$LOG_ROOT/umi-tag-run1/"
cp -a "$LOCI" "$LOG_ROOT/umi-tag-run1/locus_evidence.tsv"

run_mode none umi-none-run1 "$WORK/r1.fastq" "$WORK/r2.fastq"

python3 - <<'PY'
import shutil, subprocess, sys
print("python", sys.version.split()[0])
for cmd, args in [
    ("blastn", ["-version"]),
    ("bowtie2", ["--version"]),
    ("samtools", ["--version"]),
    ("umi_tools", ["--version"]),
]:
    out = subprocess.check_output([cmd, *args], text=True, stderr=subprocess.STDOUT)
    print(cmd, out.strip().splitlines()[0][:120])
print("executable", sys.executable)
PY

echo "DONE_UMI_LOG=$LOG_ROOT"
