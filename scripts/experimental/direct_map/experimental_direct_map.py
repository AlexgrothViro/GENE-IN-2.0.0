#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from scripts.evidence.common import (
        build_artifact_manifest,
        fsync_directory,
        merge_intervals,
        parse_intervals,
        read_fasta,
        read_tsv,
        sha256_file,
        validate_artifact_manifest,
        write_json_atomic,
        write_tsv_atomic,
    )
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence"))
    from common import (
        build_artifact_manifest,
        fsync_directory,
        merge_intervals,
        parse_intervals,
        read_fasta,
        read_tsv,
        sha256_file,
        validate_artifact_manifest,
        write_json_atomic,
        write_tsv_atomic,
    )


PROFILE_SCHEMA = "experimental-direct-map-profile-v2"
PROFILE_ID = "GENEIN-EV2-DIRECT-MAP-001.profile-v1.2"
PIPELINE_VERSION = "experimental-direct-map-1.2"
METRICS_SCHEMA = "experimental-direct-map-metrics-v2"
INVARIANTS_SCHEMA = "experimental-direct-map-invariants-v2"
COVERAGE_SCHEMA = "experimental-direct-map-coverage-v2"
OUTPUT_CONTRACTS = {
    "metrics": METRICS_SCHEMA,
    "invariants": INVARIANTS_SCHEMA,
    "coverage_tsv": COVERAGE_SCHEMA,
}
# This pipeline never promotes into the canonical Evidence V2 / Alpha.2
# flow; SUCCESS.json and direct_map_metrics.json both self-identify this so
# the dashboard and downstream consumers can refuse to reinterpret these
# artifacts as diagnostic/canonical without re-deriving it from context.
GOVERNANCE_STATE = "EXPERIMENTAL"
DIAGNOSTIC = False
# The Gene-In 1.1 / Alpha.2 build compared a frozen set of public artifacts against a
# frozen baseline commit and required every one of them to be byte-identical
# (`baseline_comparison.all_unchanged == true`). That check CANNOT run here: the frozen
# commit is absent from this repository's history, one of the three frozen artifacts no
# longer exists, and the other two are uncommitted. Rather than re-anchor the baseline to
# an arbitrary commit or delete the requirement silently, the run declares the comparison
# NOT_EXECUTED and states the guarantee it therefore does not provide. This is NOT a pass,
# and callers must not read it as one.
BASELINE_COMPARISON = {
    "schema_version": "experimental-baseline-comparison-v2",
    "comparison": "FROZEN_PUBLIC_ARTIFACTS",
    "state": "NOT_EXECUTED",
    "reason": (
        "The frozen Gene-In 1.1 (Alpha.2) baseline commit is not present in this "
        "repository history; its artifact set cannot be resolved, so no historical "
        "comparison was performed."
    ),
    "guarantee_not_provided": (
        "Preservation of the frozen public baseline artifacts is NOT verified by this "
        "run. No equivalence with Gene-In 1.1 is measured, claimed or implied."
    ),
    "substituted_by": "RUN_INTEGRITY_CHAIN",
    "run_integrity_chain": (
        "SUCCESS.json anchors the SHA-256 of artifact_manifest.json, which anchors the "
        "SHA-256 of every retained artifact; provenance records the executing source "
        "state. Tampering with any link is detectable."
    ),
}
MEASUREMENT_STATES = {"MEASURED", "NOT_MEASURED", "UNDEFINED", "NOT_APPLICABLE"}
READ_CLASSES = ("UNMAPPED", "UNIQUE", "MULTI_UNEQUAL", "EQUIVALENT_AMBIGUOUS")
CIGAR_RE = re.compile(r"(\d+)([MIDNSHP=X])")
UMI_RE = re.compile(r"#([ACGTN]+)$", re.IGNORECASE)

CLASSIFICATION_FIELDS = [
    "sample_id", "read_id", "mate", "classification", "measurement_state", "reason",
    "primary_mapq", "placement_count", "best_alignment_score", "secondary_count",
    "supplementary_count", "qc_fail_count", "mapq_unknown_count", "placements",
]
GEOMETRY_FIELDS = ["sample_id", "geometry", "templates", "reads", "measurement_state"]
COVERAGE_IDENTITY_FIELDS = [
    "schema_version", "sample_id", "scope", "reference_id", "region_id", "track", "minimum_mapq",
    "minimum_base_quality", "unit", "stage", "window_bp", "measurement_state", "reason",
    "unknown_mapq_count", "pairing_invalid_pnext_count", "pairing_filtered_mate_count",
    "pairing_filtered_mate_reasons_json",
]
COVERAGE_METRIC_FIELDS = [
    "denominator_bp", "covered_bases_1x", "covered_bases_3x", "breadth_1x", "breadth_3x",
    "depth_total", "mean_depth_complete", "median_depth_complete", "stdev_depth_complete",
    "iqr_depth_complete", "min_depth_complete", "max_depth_complete", "mean_depth_covered",
    "median_depth_covered", "min_depth_covered", "cv_depth_complete", "covered_depth_state", "cv_state",
    "max_window_depth_fraction", "concentration_state", "covered_intervals", "zero_run_count",
    "max_zero_run_bp", "histogram_json",
]
COVERAGE_FIELDS = COVERAGE_IDENTITY_FIELDS + COVERAGE_METRIC_FIELDS


@dataclass(frozen=True)
class SamRecord:
    qname: str
    flag: int
    reference: str
    position: int
    mapq: int
    cigar: str
    mate_reference: str
    mate_position: int
    sequence: str
    qualities: str
    tags: dict[str, tuple[str, str]]

    @property
    def mate(self) -> int:
        if self.flag & 0x40:
            return 1
        if self.flag & 0x80:
            return 2
        return 0

    @property
    def read_key(self) -> tuple[str, int]:
        return normalize_qname(self.qname), self.mate

    @property
    def placement_key(self) -> tuple[str, int, str, int, str, str]:
        return (
            normalize_qname(self.qname), self.mate, self.reference, self.position,
            "-" if self.flag & 0x10 else "+", self.cigar,
        )

    @property
    def mapped(self) -> bool:
        return not (self.flag & 0x4) and self.reference != "*" and self.cigar != "*"


def normalize_qname(value: str) -> str:
    # Deliberately NOT memoised. A process-global lru_cache here retained every
    # read name for the life of the process (measured: ~46 MB per 200k distinct
    # names, never released between samples) and was actually slower than the
    # plain function on first sight of each name. The pairing-index fix in
    # build_coverage_rows()/template_pairing_assessment() removed the repeated
    # whole-universe rescans that made this function hot in the first place.
    parts = value.split()
    if not parts:
        raise ValueError("read identifier cannot be empty")
    return re.sub(r"/[12]$", "", parts[0])


def load_profile(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        profile = json.load(handle)
    if not isinstance(profile, dict) or profile.get("schema_version") != PROFILE_SCHEMA:
        raise ValueError(f"profile must use schema_version {PROFILE_SCHEMA}")
    if profile.get("profile_id") != PROFILE_ID or profile.get("profile_revision") != "1.2":
        raise ValueError(f"profile identity must be {PROFILE_ID} revision 1.2")
    if profile.get("pipeline_version") != PIPELINE_VERSION:
        raise ValueError(f"profile must require pipeline_version {PIPELINE_VERSION}")
    if profile.get("output_contracts") != OUTPUT_CONTRACTS:
        raise ValueError("profile must declare the current metrics, invariants and coverage TSV contracts")
    if profile.get("profile_compatibility") != {
        "previous_profile_id": "GENEIN-EV2-DIRECT-MAP-001.profile-v1.1",
        "run_identity": "PROFILE_ID_PROFILE_SHA256_COMMIT",
        "semantic_compatibility": "INCOMPATIBLE_MAPQ255_MEASUREMENT",
    }:
        raise ValueError("profile must declare the v1.1 to v1.2 semantic incompatibility and run identity")
    grid = profile.get("grid")
    expected_grid = {
        "mapq": [0, 10, 20, 30], "baseq": [0, 20, 30],
        "tracks": ["unique", "all_eligible"], "units": ["READ", "TEMPLATE"],
        "stages": ["PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI"],
        "scopes": ["REFERENCE", "LOCUS"], "windows_bp": [20, 50, 100],
    }
    if grid != expected_grid:
        raise ValueError("direct-map grid has an invalid structure")
    if set(profile.get("measurement_states", [])) != MEASUREMENT_STATES:
        raise ValueError("experimental profile has invalid measurement states")
    aligner = profile.get("aligner", {})
    if aligner.get("mode") != "--very-sensitive-local" or aligner.get("placements_mode") != "-a":
        raise ValueError("profile must declare the two-pass Bowtie2 modes used by this implementation")
    if not isinstance(aligner.get("seed"), int):
        raise ValueError("experimental profile seed must be an integer")
    semantics = profile.get("track_semantics", {})
    if semantics.get("all_eligible_mapq_source") != "PLACEMENT" or semantics.get("unique_mapq_source") != "PRIMARY_DEFAULT_PASS":
        raise ValueError("profile tracks must declare their distinct MAPQ sources")
    cross_track = semantics.get("cross_track_unique_le_all_eligible", {})
    if (
        cross_track.get("mapq_zero") != "EVALUATE_WHEN_BOTH_CELLS_MEASURED" or
        cross_track.get("positive_thresholds") != "NOT_APPLICABLE" or
        not str(cross_track.get("reason", "")).strip()
    ):
        raise ValueError("cross-track comparison must be evaluated at MAPQ 0 and inapplicable at positive thresholds")
    if semantics.get("unknown_placement_mapq") != "MAPQ_ZERO_INCLUDED_POSITIVE_THRESHOLDS_NOT_MEASURED":
        raise ValueError("unknown placement MAPQ must be included at MAPQ 0 and unmeasured at positive thresholds")
    if semantics.get("unknown_primary_mapq") != "ALL_THRESHOLDS_NOT_MEASURED":
        raise ValueError("unknown primary MAPQ must leave unique coverage unmeasured at every threshold")
    if semantics.get("template_pairing_failure") != "TEMPLATE_CELLS_NOT_MEASURED":
        raise ValueError("unreconciled paired placements must make template coverage NOT_MEASURED")
    if semantics.get("orthogonal_count_source") != "PLACEMENTS_PASS":
        raise ValueError("orthogonal alignment counters must use the placements pass")
    if profile.get("measurement_error_scope") != {
        "primary_reconciliation": "ALL_TRACKS_ALL_THRESHOLDS",
        "template_pairing": "ALL_TEMPLATE_CELLS_PER_STAGE_TRACK_MAPQ_BASEQ_REGION_AFTER_FILTERS",
        "unknown_primary_mapq": "UNIQUE_ALL_THRESHOLDS_PER_CELL_AFTER_STAGE_AND_FILTERS",
        "unknown_placement_mapq": "ALL_ELIGIBLE_MAPQ_ZERO_INCLUDED_POSITIVE_THRESHOLDS_PER_CELL_AFTER_STAGE_AND_FILTERS",
    }:
        raise ValueError("profile measurement error scopes do not match the implementation")
    provenance = profile.get("provenance_requirements", {})
    if provenance != {
        "controls": "REQUIRED_STATE_OR_RECORDS",
        "negativeome": "REQUIRED_STATE_OR_REFERENCES",
        "panel_manifest": "REQUIRED",
    }:
        raise ValueError("experimental profile requires panel, negativeome and controls provenance")
    return profile


def load_panel_manifest(path: str | Path, reference_path: str | Path) -> dict:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8", errors="strict") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "experimental-direct-map-panel-v1":
        raise ValueError("panel manifest must use experimental-direct-map-panel-v1")
    if not isinstance(manifest.get("panel_id"), str) or not manifest["panel_id"].strip():
        raise ValueError("panel manifest requires panel_id")
    references = manifest.get("references")
    if not isinstance(references, list) or not references:
        raise ValueError("panel manifest requires reference records")
    sequences = read_fasta(reference_path)
    by_id = {}
    for record in references:
        if not isinstance(record, dict) or not isinstance(record.get("role"), str) or not record["role"].strip():
            raise ValueError("panel reference has an invalid role")
        reference_id = record.get("id")
        if reference_id in by_id or reference_id not in sequences:
            raise ValueError(f"panel reference is missing, unknown or duplicated: {reference_id!r}")
        sequence = sequences[reference_id]
        expected_hash = hashlib.sha256(sequence.encode("utf-8")).hexdigest()
        if record.get("length") != len(sequence) or record.get("sha256_sequence") != expected_hash:
            raise ValueError(f"panel reference metadata mismatch: {reference_id}")
        by_id[reference_id] = record
    if set(by_id) != set(sequences):
        raise ValueError("panel manifest references do not exactly match the selected FASTA")
    if not any(record["role"] == "TARGET" for record in references):
        raise ValueError("panel manifest requires at least one TARGET reference")

    negativeome = manifest.get("negativeome")
    if not isinstance(negativeome, dict) or negativeome.get("state") not in {"MEASURED", "NOT_APPLICABLE"}:
        raise ValueError("panel manifest requires an explicit negativeome state")
    negative_ids = sorted(reference_id for reference_id, record in by_id.items() if record["role"] == "NEGATIVEOME")
    if negativeome["state"] == "MEASURED":
        if sorted(negativeome.get("reference_ids", [])) != negative_ids or not negative_ids:
            raise ValueError("negativeome reference_ids must exactly match NEGATIVEOME panel records")
    elif negative_ids or not str(negativeome.get("reason", "")).strip():
        raise ValueError("NOT_APPLICABLE negativeome requires no NEGATIVEOME records and an explicit reason")

    controls = manifest.get("controls")
    if not isinstance(controls, dict) or controls.get("state") not in {"MEASURED", "NOT_APPLICABLE"}:
        raise ValueError("panel manifest requires an explicit controls state")
    control_reference_ids = sorted(
        reference_id for reference_id, record in by_id.items()
        if record["role"] in {"CONTROL", "LOW_COMPLEXITY_CONTROL"}
    )
    if controls["state"] == "MEASURED":
        records = controls.get("records")
        if not isinstance(records, list) or not records:
            raise ValueError("MEASURED controls require non-empty records")
        control_ids = set()
        for record in records:
            if not isinstance(record, dict) or not all(str(record.get(key, "")).strip() for key in ("id", "role", "source", "sha256")):
                raise ValueError("control record requires id, role, source and sha256")
            if record["id"] in control_ids or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
                raise ValueError("control record ids must be unique and sha256 must be lowercase hexadecimal")
            control_ids.add(record["id"])
    elif control_reference_ids or not str(controls.get("reason", "")).strip():
        raise ValueError("NOT_APPLICABLE controls require no control-role references and an explicit reason")
    return manifest


def parse_sam(path: str | Path) -> list[SamRecord]:
    records: list[SamRecord] = []
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.startswith("@"):
                continue
            cols = raw.rstrip("\r\n").split("\t")
            if len(cols) < 11:
                raise ValueError(f"{path}:{line_number}: SAM row has fewer than 11 columns")
            try:
                flag, position, mapq, mate_position = map(int, (cols[1], cols[3], cols[4], cols[7]))
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid SAM numeric field") from exc
            tags: dict[str, tuple[str, str]] = {}
            for tag in cols[11:]:
                parts = tag.split(":", 2)
                if len(parts) == 3:
                    tags[parts[0]] = (parts[1], parts[2])
            records.append(SamRecord(
                qname=cols[0], flag=flag, reference=cols[2], position=position, mapq=mapq,
                cigar=cols[5], mate_reference=cols[6], mate_position=mate_position,
                sequence=cols[9], qualities=cols[10], tags=tags,
            ))
    return records


def _open_fastq(path: Path):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="strict")
    return path.open("r", encoding="utf-8", errors="strict")


def fastq_read_keys(path: str | Path, mate: int) -> list[tuple[str, int]]:
    keys = []
    with _open_fastq(Path(path)) as handle:
        record_no = 0
        while True:
            lines = [handle.readline() for _ in range(4)]
            if not any(lines):
                break
            record_no += 1
            if any(line == "" for line in lines) or not lines[0].startswith("@"):
                raise ValueError(f"invalid FASTQ record {record_no}: {path}")
            keys.append((normalize_qname(lines[0][1:].strip()), mate))
    if not keys:
        raise ValueError(f"FASTQ has no reads: {path}")
    if len(keys) != len(set(keys)):
        raise ValueError(f"FASTQ read identifiers are not unique: {path}")
    return keys


def _alignment_score(record: SamRecord) -> int | None:
    tag = record.tags.get("AS")
    if not tag:
        return None
    try:
        return int(tag[1])
    except ValueError:
        return None


def classify_reads(
    input_keys: list[tuple[str, int]], primary_records: list[SamRecord], placement_records: list[SamRecord],
) -> tuple[dict[tuple[str, int], dict], list[str]]:
    primary_by_read: dict[tuple[str, int], list[SamRecord]] = defaultdict(list)
    all_by_read: dict[tuple[str, int], list[SamRecord]] = defaultdict(list)
    orthogonal: dict[tuple[str, int], Counter] = defaultdict(Counter)
    for record in primary_records:
        if record.mapped and not (record.flag & (0x100 | 0x800 | 0x200)):
            primary_by_read[record.read_key].append(record)
    for record in placement_records:
        key = record.read_key
        if record.flag & 0x100:
            orthogonal[key]["secondary"] += 1
        if record.flag & 0x800:
            orthogonal[key]["supplementary"] += 1
        if record.flag & 0x200:
            orthogonal[key]["qc_fail"] += 1
        if record.mapq == 255:
            orthogonal[key]["mapq_unknown"] += 1
        if record.mapped and not (record.flag & (0x800 | 0x200)):
            all_by_read[key].append(record)

    classifications: dict[tuple[str, int], dict] = {}
    errors: list[str] = []
    known = set(input_keys)
    unexpected = (set(primary_by_read) | set(all_by_read)) - known
    if unexpected:
        errors.append("SAM contains reads absent from validated FASTQ: " + ", ".join(map(str, sorted(unexpected))))
    for key in input_keys:
        primary = primary_by_read.get(key, [])
        placements_by_key = {record.placement_key: record for record in all_by_read.get(key, [])}
        placements = list(placements_by_key.values())
        state, reason = "MEASURED", ""
        classification: str | None = None
        primary_mapq: int | None = None
        best_score: int | None = None
        if placements:
            if len(primary) != 1:
                state, reason = "NOT_MEASURED", "primary/all-pass reconciliation requires one primary alignment"
            elif primary[0].placement_key not in placements_by_key:
                state, reason = "NOT_MEASURED", "primary placement is absent from the -a pass"
            else:
                primary_mapq = primary[0].mapq
                scores = [_alignment_score(record) for record in placements]
                if any(score is None for score in scores):
                    state, reason = "NOT_MEASURED", "placement lacks an integer AS tag"
                elif len(placements) == 1:
                    classification = "UNIQUE"
                    best_score = scores[0]
                else:
                    assert all(score is not None for score in scores)
                    numeric_scores = [int(score) for score in scores]
                    best_score = max(numeric_scores)
                    classification = (
                        "EQUIVALENT_AMBIGUOUS" if len(set(numeric_scores)) == 1 else "MULTI_UNEQUAL"
                    )
        elif primary:
            state, reason = "NOT_MEASURED", "primary pass mapped the read but -a pass has no placement"
        elif orthogonal.get(key, Counter()).get("qc_fail", 0):
            state, reason = "NOT_MEASURED", "all observed placements failed SAM QC"
        elif orthogonal.get(key, Counter()).get("supplementary", 0):
            state, reason = "NOT_MEASURED", "only supplementary placement was observed"
        else:
            classification = "UNMAPPED"
        classifications[key] = {
            "classification": classification, "measurement_state": state, "reason": reason,
            "primary_mapq": primary_mapq, "placement_count": len(placements),
            "best_alignment_score": best_score, "placements": placements,
            **orthogonal.get(key, Counter()),
        }
        if state != "MEASURED":
            errors.append(f"{key[0]}/{key[1]}: {reason}")
    return classifications, errors


def classification_rows(sample: str, classifications: dict[tuple[str, int], dict]) -> list[dict]:
    rows = []
    for (read_id, mate), item in sorted(classifications.items()):
        placements = sorted("|".join(map(str, record.placement_key[2:])) for record in item["placements"])
        rows.append({
            "sample_id": sample, "read_id": read_id, "mate": mate,
            "classification": item["classification"], "measurement_state": item["measurement_state"],
            "reason": item["reason"], "primary_mapq": item["primary_mapq"],
            "placement_count": item["placement_count"],
            "best_alignment_score": item["best_alignment_score"],
            "secondary_count": item.get("secondary", 0),
            "supplementary_count": item.get("supplementary", 0),
            "qc_fail_count": item.get("qc_fail", 0),
            "mapq_unknown_count": item.get("mapq_unknown", 0),
            "placements": ";".join(placements),
        })
    return rows


def geometry_rows(
    sample: str, input_keys: list[tuple[str, int]], primary_records: list[SamRecord], paired: bool,
) -> list[dict]:
    mapped_by_template: dict[str, dict[int, SamRecord]] = defaultdict(dict)
    for record in primary_records:
        if record.mapped and not (record.flag & (0x100 | 0x800 | 0x200)):
            mapped_by_template[normalize_qname(record.qname)][record.mate] = record
    templates = sorted({name for name, _ in input_keys})
    counts: Counter = Counter()
    reads: Counter = Counter()
    for name in templates:
        records = mapped_by_template.get(name, {})
        if not paired:
            geometry = "single_end"
            read_count = 1
        elif 1 in records and 2 in records:
            geometry = "proper" if (records[1].flag & 0x2 and records[2].flag & 0x2) else "discordant"
            read_count = 2
        elif records:
            geometry, read_count = "orphan", 2
        else:
            geometry, read_count = "unmapped_pair", 2
        counts[geometry] += 1
        reads[geometry] += read_count
    order = ["proper", "discordant", "orphan", "unmapped_pair"] if paired else ["single_end"]
    return [{
        "sample_id": sample, "geometry": name, "templates": counts[name], "reads": reads[name],
        "measurement_state": "MEASURED",
    } for name in order]


def cigar_covered_positions(record: SamRecord, minimum_baseq: int) -> set[int]:
    operations = [(int(size), op) for size, op in CIGAR_RE.findall(record.cigar)]
    if not operations or "".join(f"{size}{op}" for size, op in operations) != record.cigar:
        raise ValueError(f"invalid CIGAR for {record.qname}: {record.cigar}")
    query_index = 0
    reference_position = record.position
    result: set[int] = set()
    qualities = [] if record.qualities == "*" else [ord(char) - 33 for char in record.qualities]
    for size, op in operations:
        if op in {"M", "=", "X"}:
            if not qualities or query_index + size > len(qualities):
                raise ValueError(f"missing/truncated base qualities for {record.qname}")
            for offset in range(size):
                if qualities[query_index + offset] >= minimum_baseq:
                    result.add(reference_position + offset)
            query_index += size
            reference_position += size
        elif op in {"I", "S"}:
            query_index += size
        elif op in {"D", "N"}:
            reference_position += size
        elif op in {"H", "P"}:
            continue
    return result


def _primary_records_by_template(records: Iterable[SamRecord]) -> dict[str, list[SamRecord]]:
    result: dict[str, list[SamRecord]] = defaultdict(list)
    for record in records:
        if record.mapped and not (record.flag & (0x100 | 0x800 | 0x200)):
            result[normalize_qname(record.qname)].append(record)
    return result


def stage_templates(
    input_keys: list[tuple[str, int]], primary_records: list[SamRecord], umi_mode: str,
) -> tuple[dict[str, set[str]], dict[str, tuple[str, str]]]:
    templates = sorted({name for name, _ in input_keys})
    primary = _primary_records_by_template(primary_records)
    coordinate_groups: dict[tuple, list[str]] = defaultdict(list)
    for name in templates:
        signature = tuple(sorted(record.placement_key[2:] for record in primary.get(name, [])))
        coordinate_groups[("MAPPED", signature) if signature else ("UNMAPPED", name)].append(name)
    coordinate_keep = {sorted(names)[0] for names in coordinate_groups.values()}
    stages = {"PRE_DEDUP": set(templates), "POST_COORDINATE_EXCLUSION": coordinate_keep}
    states = {
        "PRE_DEDUP": ("MEASURED", ""),
        "POST_COORDINATE_EXCLUSION": ("MEASURED", "coordinate exclusion ablation"),
    }
    if umi_mode == "none":
        stages["POST_UMI"] = set()
        states["POST_UMI"] = ("NOT_APPLICABLE", "UMI was not declared")
        return stages, states

    umi_groups: dict[tuple, list[str]] = defaultdict(list)
    missing = []
    for name in templates:
        if umi_mode == "read_name":
            match = UMI_RE.search(name)
            umi = match.group(1).upper() if match else None
        else:
            values = {record.tags.get("RX", ("", ""))[1] for record in primary.get(name, [])}
            values.discard("")
            umi = next(iter(values)) if len(values) == 1 else None
        if not umi:
            missing.append(name)
            continue
        signature = tuple(sorted(record.placement_key[2:] for record in primary.get(name, [])))
        group_key = ("MAPPED", signature, umi) if signature else ("UNMAPPED", name, umi)
        umi_groups[group_key].append(name)
    if missing:
        stages["POST_UMI"] = set()
        states["POST_UMI"] = ("NOT_MEASURED", "declared UMI is missing or inconsistent")
    else:
        stages["POST_UMI"] = {sorted(names)[0] for names in umi_groups.values()}
        states["POST_UMI"] = ("MEASURED", f"{umi_mode} UMI ablation")
    return stages, states


def summarize_stage_states(
    stages: dict[str, set[str]], stage_states: dict[str, tuple[str, str]],
) -> dict[str, dict]:
    return {
        name: {
            "state": state, "reason": reason,
            "retained_templates": len(stages[name]) if state == "MEASURED" else None,
        }
        for name, (state, reason) in stage_states.items()
    }


def eligible_records(
    records: list[SamRecord], classifications: dict[tuple[str, int], dict], track: str,
    keep_templates: set[str], minimum_mapq: int,
) -> list[SamRecord]:
    selected = []
    seen: set[tuple] = set()
    for record in records:
        name = normalize_qname(record.qname)
        if name not in keep_templates or not record.mapped or record.flag & (0x800 | 0x200):
            continue
        item = classifications.get(record.read_key)
        if not item or item["measurement_state"] != "MEASURED":
            continue
        if track == "unique" and item["classification"] != "UNIQUE":
            continue
        effective_mapq = record.mapq if track == "all_eligible" else item["primary_mapq"]
        if track == "all_eligible" and effective_mapq == 255:
            if minimum_mapq > 0:
                raise ValueError("all_eligible placement MAPQ is unknown (255); positive-threshold coverage must be NOT_MEASURED")
        elif effective_mapq is None or effective_mapq == 255 or effective_mapq < minimum_mapq:
            continue
        if record.placement_key in seen:
            continue
        seen.add(record.placement_key)
        selected.append(record)
    return selected


def records_overlapping_cell(
    records: list[SamRecord], reference_id: str, coordinates: list[int], minimum_baseq: int,
) -> list[SamRecord]:
    coordinate_set = set(coordinates)
    return [
        record for record in records
        if record.mapped and record.reference == reference_id and
        cigar_covered_positions(record, minimum_baseq) & coordinate_set
    ]


def validate_alignment_references(
    primary_records: list[SamRecord], placement_records: list[SamRecord], reference_lengths: dict[str, int],
) -> None:
    unknown_by_source = {}
    for source, records in (("primary", primary_records), ("placements", placement_records)):
        unknown = sorted({record.reference for record in records if record.mapped and record.reference not in reference_lengths})
        if unknown:
            unknown_by_source[source] = unknown
    if unknown_by_source:
        details = "; ".join(f"{source}={','.join(references)}" for source, references in unknown_by_source.items())
        raise ValueError(f"mapped alignment references sequence absent from declared FASTA: {details}")


def cell_unknown_mapq_count(
    records: list[SamRecord], classifications: dict[tuple[str, int], dict], track: str,
    keep_templates: set[str],
) -> int:
    unknown: set[tuple] = set()
    for record in records:
        name = normalize_qname(record.qname)
        if name not in keep_templates or not record.mapped or record.flag & (0x800 | 0x200):
            continue
        item = classifications.get(record.read_key)
        if not item or item["measurement_state"] != "MEASURED":
            continue
        if track == "unique":
            if item["classification"] != "UNIQUE" or item["primary_mapq"] != 255:
                continue
        elif track == "all_eligible":
            if record.mapq != 255:
                continue
        else:
            raise ValueError(f"unsupported coverage track: {track}")
        unknown.add(record.placement_key)
    return len(unknown)


def _mate_index(records: list[SamRecord], index: int, used: set[int]) -> int | None:
    record = records[index]
    if not (record.flag & 0x1) or record.flag & 0x8 or record.mate_position <= 0:
        return None
    mate_ref = record.reference if record.mate_reference == "=" else record.mate_reference
    for candidate_index, candidate in enumerate(records):
        if candidate_index == index or candidate_index in used or candidate.mate == record.mate:
            continue
        candidate_mate_ref = candidate.reference if candidate.mate_reference == "=" else candidate.mate_reference
        if (
            candidate.reference == mate_ref and candidate.position == record.mate_position and
            candidate_mate_ref == record.reference and candidate.mate_position == record.position
        ):
            return candidate_index
    return None


def template_pairing_issue(records: list[SamRecord], universe: list[SamRecord] | None = None) -> str | None:
    return template_pairing_assessment(records, universe or records)["reason"]


def template_pairing_assessment(
    records: list[SamRecord], universe: list[SamRecord] | dict[str, list[SamRecord]], *,
    baseq0_records: list[SamRecord] | None = None, cell_records: list[SamRecord] | None = None,
    keep_templates: set[str] | None = None, classifications: dict[tuple[str, int], dict] | None = None,
    track: str | None = None, minimum_mapq: int | None = None,
    universe_position_index: dict[str, dict[tuple[str, int], list[SamRecord]]] | None = None,
) -> dict:
    by_template: dict[str, list[SamRecord]] = defaultdict(list)
    for record in records:
        by_template[normalize_qname(record.qname)].append(record)
    # build_coverage_rows calls this once per (stage x track x mapq x baseq x
    # region) grid cell with the same genome-wide `pairing_universe` dict
    # (keyed by every template in the run, not just this cell's selection);
    # copying it into a fresh dict on every call made the whole grid scale
    # with total_templates x cells instead of just this cell's record count,
    # which is what made highly multi-mapped panels time out. Look up
    # directly into the caller's dict/list instead of re-copying it.
    if isinstance(universe, dict):
        universe_by_template = universe
    else:
        universe_by_template = defaultdict(list)
        for record in universe:
            universe_by_template[normalize_qname(record.qname)].append(record)
    invalid = 0
    filtered = Counter()
    baseq0_keys = {record.placement_key for record in (baseq0_records or records)}
    cell_keys = {record.placement_key for record in (cell_records or records)}
    # For a template with k placements in the universe (e.g. a read that
    # multi-maps into a repetitive/low-complexity locus), the original
    # implementation re-scanned all k universe candidates with a fresh
    # _mate_index([record, candidate], ...) call for every one of the
    # (stage x track x mapq x baseq x region) grid cells that leaves this
    # record unmatched -- O(k) per lookup, repeated across the whole grid.
    # A reciprocal mate must sit at the exact (reference, position) the
    # record's own mate fields point to, so indexing universe candidates by
    # that position once per template turns each lookup into an O(1)
    # dict access plus a scan of same-position candidates (normally just
    # one), which is equivalent because every non-matching position was
    # already being skipped by the checks below -- just after an O(k) scan.
    # Callers that reassess the same universe across many grid cells (i.e.
    # build_coverage_rows) pass a precomputed/shared index in so it is built
    # once for the whole grid instead of once per cell.
    position_index_cache: dict[str, dict[tuple[str, int], list[SamRecord]]] = (
        universe_position_index if universe_position_index is not None else {}
    )
    for template_name, template_records in by_template.items():
        ordered = sorted(template_records, key=lambda record: record.placement_key)
        used: set[int] = set()
        for index, record in enumerate(ordered):
            if index in used:
                continue
            expects_mapped_mate = bool(record.flag & 0x1) and not bool(record.flag & 0x8)
            mate_index = _mate_index(ordered, index, used)
            if expects_mapped_mate and mate_index is None:
                mate = None
                if record.mate_position > 0:
                    if template_name not in position_index_cache:
                        position_index: dict[tuple[str, int], list[SamRecord]] = defaultdict(list)
                        for candidate in sorted(
                            universe_by_template.get(template_name, []), key=lambda item: item.placement_key,
                        ):
                            position_index[(candidate.reference, candidate.position)].append(candidate)
                        position_index_cache[template_name] = position_index
                    mate_ref = record.reference if record.mate_reference == "=" else record.mate_reference
                    for candidate in position_index_cache[template_name].get((mate_ref, record.mate_position), []):
                        if candidate.placement_key == record.placement_key or candidate.mate == record.mate:
                            continue
                        candidate_mate_ref = (
                            candidate.reference if candidate.mate_reference == "=" else candidate.mate_reference
                        )
                        if candidate_mate_ref == record.reference and candidate.mate_position == record.position:
                            mate = candidate
                            break
                if mate is None:
                    invalid += 1
                    continue
                if mate.placement_key not in baseq0_keys:
                    filtered["REGION"] += 1
                elif mate.placement_key not in cell_keys:
                    filtered["BASEQ"] += 1
                elif classifications is not None and track is not None and minimum_mapq is not None:
                    if eligible_records([mate], classifications, track, {template_name}, minimum_mapq):
                        filtered["OTHER"] += 1
                    else:
                        item = classifications.get(mate.read_key)
                        if track == "unique" and (not item or item.get("classification") != "UNIQUE"):
                            filtered["TRACK"] += 1
                        else:
                            filtered["MAPQ"] += 1
                else:
                    filtered["OTHER"] += 1
            if mate_index is not None:
                used.update((index, mate_index))
    reason = None
    if invalid:
        reason = f"{invalid} selected paired placement(s) have no exact reciprocal PNEXT in mapped input"
    return {
        "invalid_pnext_count": invalid,
        "filtered_mate_count": sum(filtered.values()),
        "filtered_mate_reasons": dict(sorted(filtered.items())),
        "reason": reason,
    }


def template_events(records: list[SamRecord], minimum_baseq: int) -> list[tuple[str, set[int]]]:
    events: list[tuple[str, set[int]]] = []
    by_template: dict[str, list[SamRecord]] = defaultdict(list)
    for record in records:
        by_template[normalize_qname(record.qname)].append(record)
    for template_records in by_template.values():
        remaining = sorted(template_records, key=lambda r: r.placement_key)
        used: set[int] = set()
        for index, record in enumerate(remaining):
            if index in used:
                continue
            mate_index = _mate_index(remaining, index, used)
            first = cigar_covered_positions(record, minimum_baseq)
            if mate_index is None:
                events.append((record.reference, first))
                used.add(index)
                continue
            mate = remaining[mate_index]
            second = cigar_covered_positions(mate, minimum_baseq)
            if mate.reference == record.reference:
                events.append((record.reference, first | second))
            else:
                events.extend(((record.reference, first), (mate.reference, second)))
            used.update({index, mate_index})
    return events


def coverage_depth(
    records: list[SamRecord], reference_lengths: dict[str, int], unit: str, minimum_baseq: int,
) -> dict[str, list[int]]:
    depth = {reference: [0] * length for reference, length in reference_lengths.items()}
    if unit == "READ":
        events = [(record.reference, cigar_covered_positions(record, minimum_baseq)) for record in records]
    else:
        events = template_events(records, minimum_baseq)
    for reference, positions in events:
        if reference not in depth:
            raise ValueError(f"alignment references sequence absent from FASTA: {reference}")
        for position in positions:
            if position < 1 or position > len(depth[reference]):
                raise ValueError(f"alignment position outside reference: {reference}:{position}")
            depth[reference][position - 1] += 1
    return depth


def percentile(values: list[int], fraction: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    point = (len(ordered) - 1) * fraction
    low, high = math.floor(point), math.ceil(point)
    if low == high:
        return float(ordered[low])
    return ordered[low] + (ordered[high] - ordered[low]) * (point - low)


def _interval_text(positions: list[int]) -> str:
    return ";".join(f"{left}-{right}" for left, right in merge_intervals((p, p) for p in positions))


def _zero_runs(depths: list[int]) -> tuple[int, int]:
    runs: list[int] = []
    current = 0
    for value in depths:
        if value == 0:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return len(runs), max(runs, default=0)


def _window_maximum(segments: list[list[int]], window_bp: int) -> int | None:
    maximum: int | None = None
    for segment in segments:
        if len(segment) < window_bp:
            continue
        current = sum(segment[:window_bp])
        segment_maximum = current
        for index in range(window_bp, len(segment)):
            current += segment[index] - segment[index - window_bp]
            segment_maximum = max(segment_maximum, current)
        maximum = segment_maximum if maximum is None else max(maximum, segment_maximum)
    return maximum


def measured_metrics(
    depths: list[int], coordinates: list[int], window_bp: int, intervals: list[tuple[int, int]] | None = None,
) -> tuple[dict, dict]:
    intervals = intervals or merge_intervals((position, position) for position in coordinates)
    segments = [[depths[position - 1] for position in range(left, right + 1)] for left, right in intervals]
    selected = [value for segment in segments for value in segment]
    denominator = len(selected)
    covered = [value for value in selected if value > 0]
    total = sum(selected)
    histogram = dict(sorted(Counter(selected).items()))
    covered_positions = [position for position, value in zip(coordinates, selected) if value > 0]
    zero_runs = [_zero_runs(segment) for segment in segments]
    zero_run_count = sum(count for count, _ in zero_runs)
    max_zero_run = max((maximum for _, maximum in zero_runs), default=0)
    complete_mean = total / denominator
    complete_stdev = statistics.pstdev(selected)
    q1, q3 = percentile(selected, 0.25), percentile(selected, 0.75)
    window_maximum = _window_maximum(segments, window_bp) if window_bp <= denominator else None
    window_applicable = window_bp <= denominator and window_maximum is not None
    concentration = window_maximum / total if window_applicable and total else None
    covered_mean = sum(covered) / len(covered) if covered else None
    covered_median = statistics.median(covered) if covered else None
    covered_min = min(covered) if covered else None
    cv = complete_stdev / complete_mean if complete_mean else None
    flat = {
        "denominator_bp": denominator, "covered_bases_1x": len(covered),
        "covered_bases_3x": sum(value >= 3 for value in selected),
        "breadth_1x": len(covered) / denominator,
        "breadth_3x": sum(value >= 3 for value in selected) / denominator,
        "depth_total": total, "mean_depth_complete": complete_mean,
        "median_depth_complete": statistics.median(selected),
        "stdev_depth_complete": complete_stdev, "iqr_depth_complete": q3 - q1,
        "min_depth_complete": min(selected), "max_depth_complete": max(selected),
        "mean_depth_covered": covered_mean, "median_depth_covered": covered_median,
        "min_depth_covered": covered_min, "cv_depth_complete": cv,
        "covered_depth_state": "MEASURED" if covered else "UNDEFINED",
        "cv_state": "MEASURED" if cv is not None else "UNDEFINED",
        "max_window_depth_fraction": concentration,
        "concentration_state": (
            "NOT_APPLICABLE" if not window_applicable else "MEASURED" if concentration is not None else "UNDEFINED"
        ),
        "covered_intervals": _interval_text(covered_positions), "zero_run_count": zero_run_count,
        "max_zero_run_bp": max_zero_run,
        "histogram_json": json.dumps(histogram, sort_keys=True, separators=(",", ":")),
    }
    reason_covered = None if covered else "no covered positions"
    reason_ratio = None if total else "zero depth has no non-zero denominator"
    reason_window = (
        f"window {window_bp} bp exceeds every contiguous interval in the {denominator} bp region"
        if not window_applicable else reason_ratio
    )
    structured = {
        name: {"state": "MEASURED", "value": value, "reason": None}
        for name, value in flat.items()
        if name not in {"covered_depth_state", "cv_state", "concentration_state"}
    }
    for name in ("mean_depth_covered", "median_depth_covered", "min_depth_covered"):
        structured[name] = {
            "state": "MEASURED" if covered else "UNDEFINED",
            "value": flat[name], "reason": reason_covered,
        }
    structured["cv_depth_complete"] = {
        "state": "MEASURED" if cv is not None else "UNDEFINED", "value": cv, "reason": reason_ratio,
    }
    structured["max_window_depth_fraction"] = {
        "state": "NOT_APPLICABLE" if not window_applicable else "MEASURED" if concentration is not None else "UNDEFINED",
        "value": concentration, "reason": reason_window,
    }
    return flat, structured


def unavailable_metrics(state: str, reason: str, denominator_bp: int) -> tuple[dict, dict]:
    flat = {field: "" for field in COVERAGE_METRIC_FIELDS}
    flat.update({
        "denominator_bp": denominator_bp,
        "covered_depth_state": state, "cv_state": state, "concentration_state": state,
        "histogram_json": "",
    })
    structured = {
        field: {"state": state, "value": None, "reason": reason}
        for field in COVERAGE_METRIC_FIELDS
        if field not in {"covered_depth_state", "cv_state", "concentration_state"}
    }
    structured["denominator_bp"] = {"state": "MEASURED", "value": denominator_bp, "reason": None}
    return flat, structured


def load_regions(reference_lengths: dict[str, int], loci_path: str | Path) -> list[dict]:
    regions = [{
        "scope": "REFERENCE", "reference_id": reference, "region_id": f"REFERENCE::{reference}",
        "coordinates": list(range(1, length + 1)), "intervals": [(1, length)],
    } for reference, length in sorted(reference_lengths.items())]
    loci = read_tsv(loci_path)
    required = {"locus_id", "sseqid", "reference_intervals"}
    if not loci or not required.issubset(loci[0]):
        raise ValueError("loci TSV must contain locus_id, sseqid and reference_intervals")
    seen = set()
    for row in loci:
        reference = row["sseqid"]
        if reference not in reference_lengths:
            raise ValueError(f"locus references unknown sequence: {reference}")
        key = (reference, row["locus_id"])
        if key in seen:
            raise ValueError(f"duplicate locus: {key}")
        seen.add(key)
        intervals = merge_intervals(parse_intervals(row["reference_intervals"]))
        coordinates = [position for left, right in intervals for position in range(left, right + 1)]
        if not coordinates or min(coordinates) < 1 or max(coordinates) > reference_lengths[reference]:
            raise ValueError(f"locus outside reference bounds: {key}")
        regions.append({
            "scope": "LOCUS", "reference_id": reference, "region_id": row["locus_id"],
            "coordinates": coordinates, "intervals": intervals,
        })
    return regions


def build_coverage_rows(
    sample: str, profile: dict, reference_lengths: dict[str, int], regions: list[dict],
    placement_records: list[SamRecord], classifications: dict[tuple[str, int], dict],
    stages: dict[str, set[str]], stage_states: dict[str, tuple[str, str]], reconciliation_errors: list[str],
    paired: bool,
) -> tuple[list[dict], list[dict]]:
    flat_rows: list[dict] = []
    structured_rows: list[dict] = []
    grid = profile["grid"]
    cell_records_cache: dict[tuple, list[SamRecord]] = {}
    baseq0_records_cache: dict[tuple, list[SamRecord]] = {}
    unknown_mapq_cache: dict[tuple, int] = {}
    pairing_universe: dict[str, list[SamRecord]] = defaultdict(list)
    for record in placement_records:
        pairing_universe[normalize_qname(record.qname)].append(record)
    # template_pairing_assessment() runs once per (stage x track x mapq x
    # baseq x region) grid cell below; pairing_universe never changes across
    # those calls, so its by-position index is built once here and reused,
    # instead of being rebuilt per template on every cell (which used to
    # scale with total_templates x cells for multi-mapped panels).
    universe_position_index: dict[str, dict[tuple[str, int], list[SamRecord]]] = {}
    for template_name, template_records in pairing_universe.items():
        index: dict[tuple[str, int], list[SamRecord]] = defaultdict(list)
        for candidate in sorted(template_records, key=lambda item: item.placement_key):
            index[(candidate.reference, candidate.position)].append(candidate)
        universe_position_index[template_name] = index
    for stage in grid["stages"]:
        stage_state, stage_reason = stage_states[stage]
        for track in grid["tracks"]:
            for minimum_mapq in grid["mapq"]:
                for minimum_baseq in grid["baseq"]:
                    for region in regions:
                        cell_key = (
                            region["scope"], region["reference_id"], region["region_id"], minimum_baseq,
                        )
                        if stage_state == "MEASURED" and cell_key not in cell_records_cache:
                            cell_records_cache[cell_key] = records_overlapping_cell(
                                placement_records, region["reference_id"], region["coordinates"], minimum_baseq,
                            )
                        cell_records = cell_records_cache.get(cell_key, [])
                        unknown_key = (stage, track, *cell_key)
                        if stage_state == "MEASURED" and unknown_key not in unknown_mapq_cache:
                            unknown_mapq_cache[unknown_key] = cell_unknown_mapq_count(
                                cell_records, classifications, track, stages[stage],
                            )
                        unknown_mapq_count = unknown_mapq_cache.get(unknown_key) if stage_state == "MEASURED" else None
                        threshold_errors = []
                        if unknown_mapq_count:
                            if track == "unique":
                                threshold_errors.append(
                                    f"primary MAPQ is unknown (255) for {unknown_mapq_count} eligible placement(s) in this cell"
                                )
                            elif minimum_mapq > 0:
                                threshold_errors.append(
                                    f"placement MAPQ is unknown (255) for {unknown_mapq_count} eligible placement(s) in this cell"
                                )
                        errors = [*reconciliation_errors, *threshold_errors]
                        if stage_state != "MEASURED":
                            state, reason = stage_state, stage_reason
                        elif errors:
                            state, reason = "NOT_MEASURED", "; ".join(errors[:10])
                        else:
                            state, reason = "MEASURED", stage_reason
                        selected = eligible_records(
                            cell_records, classifications, track, stages[stage], minimum_mapq,
                        ) if state == "MEASURED" else []
                        for unit in grid["units"]:
                            pairing = None
                            if unit == "TEMPLATE" and paired and state == "MEASURED":
                                baseq0_key = (region["scope"], region["reference_id"], region["region_id"])
                                if baseq0_key not in baseq0_records_cache:
                                    baseq0_records_cache[baseq0_key] = records_overlapping_cell(
                                        placement_records, region["reference_id"], region["coordinates"], 0,
                                    )
                                pairing = template_pairing_assessment(
                                    selected, pairing_universe, baseq0_records=baseq0_records_cache[baseq0_key],
                                    cell_records=cell_records, keep_templates=stages[stage],
                                    classifications=classifications, track=track, minimum_mapq=minimum_mapq,
                                    universe_position_index=universe_position_index,
                                )
                            if pairing and pairing["reason"]:
                                unit_state, unit_reason = "NOT_MEASURED", pairing["reason"]
                            else:
                                unit_state, unit_reason = state, reason
                            depth = coverage_depth(
                                selected, reference_lengths, unit, minimum_baseq,
                            ) if unit_state == "MEASURED" else {}
                            for window_bp in grid["windows_bp"]:
                                identity = {
                                    "schema_version": COVERAGE_SCHEMA,
                                    "sample_id": sample, "scope": region["scope"],
                                    "reference_id": region["reference_id"], "region_id": region["region_id"],
                                    "track": track, "minimum_mapq": minimum_mapq,
                                    "minimum_base_quality": minimum_baseq, "unit": unit, "stage": stage,
                                    "window_bp": window_bp, "measurement_state": unit_state, "reason": unit_reason,
                                    "unknown_mapq_count": unknown_mapq_count,
                                    "pairing_invalid_pnext_count": pairing["invalid_pnext_count"] if pairing else None,
                                    "pairing_filtered_mate_count": pairing["filtered_mate_count"] if pairing else None,
                                    "pairing_filtered_mate_reasons_json": (
                                        json.dumps(pairing["filtered_mate_reasons"], sort_keys=True, separators=(",", ":"))
                                        if pairing else None
                                    ),
                                }
                                if unit_state == "MEASURED":
                                    flat, structured = measured_metrics(
                                        depth[region["reference_id"]], region["coordinates"], window_bp,
                                        region["intervals"],
                                    )
                                else:
                                    flat, structured = unavailable_metrics(
                                        unit_state, unit_reason, len(region["coordinates"]),
                                    )
                                flat_rows.append({**identity, **flat})
                                structured_rows.append({**identity, "metrics": structured})
    return flat_rows, structured_rows


def validate_invariants(
    input_keys: list[tuple[str, int]], classifications: dict[tuple[str, int], dict],
    geometry: list[dict], coverage: list[dict], paired: bool,
) -> tuple[list[str], int, dict]:
    violations = []
    evaluated = 0
    mapq_checks: Counter = Counter()
    baseq_checks: Counter = Counter()
    measured_classes = Counter(
        item["classification"] for item in classifications.values() if item["measurement_state"] == "MEASURED"
    )
    not_measured = sum(item["measurement_state"] != "MEASURED" for item in classifications.values())
    if sum(measured_classes.values()) + not_measured != len(input_keys):
        violations.append("read classes do not sum to input reads")
    evaluated += 1
    expected_templates = len({name for name, _ in input_keys})
    if sum(row["templates"] for row in geometry) != expected_templates:
        violations.append("geometries do not sum to input templates")
    evaluated += 1
    if sum(row["reads"] for row in geometry) != len(input_keys):
        violations.append("geometry read counts do not sum to input reads")
    evaluated += 1
    measured_rows = [row for row in coverage if row["measurement_state"] == "MEASURED"]
    for row in measured_rows:
        histogram = {int(key): int(value) for key, value in json.loads(row["histogram_json"]).items()}
        if sum(histogram.values()) != row["denominator_bp"]:
            violations.append("depth histogram does not sum to denominator")
        if sum(depth * count for depth, count in histogram.items()) != row["depth_total"]:
            violations.append("weighted histogram does not equal depth total")
        if row["breadth_3x"] > row["breadth_1x"]:
            violations.append("breadth 3x exceeds breadth 1x")
        evaluated += 3
    monotonic_metrics = ("depth_total", "breadth_1x", "breadth_3x")
    comparison: dict[tuple, dict[int, dict[int, dict]]] = defaultdict(lambda: defaultdict(dict))
    for row in measured_rows:
        key = tuple(row[field] for field in (
            "scope", "reference_id", "region_id", "track", "unit", "stage", "window_bp",
        ))
        comparison[key][row["minimum_mapq"]][row["minimum_base_quality"]] = row
    for matrix in comparison.values():
        mapqs = sorted(matrix)
        for lower_mapq, higher_mapq in zip(mapqs, mapqs[1:]):
            for baseq in sorted(set(matrix[lower_mapq]) & set(matrix[higher_mapq])):
                for metric in monotonic_metrics:
                    if matrix[higher_mapq][baseq][metric] > matrix[lower_mapq][baseq][metric]:
                        violations.append(f"raising MAPQ increased {metric}")
                    evaluated += 1
                    mapq_checks[matrix[lower_mapq][baseq]["track"]] += 1
        for mapq, by_baseq in matrix.items():
            baseqs = sorted(by_baseq)
            for lower_baseq, higher_baseq in zip(baseqs, baseqs[1:]):
                for metric in monotonic_metrics:
                    if by_baseq[higher_baseq][metric] > by_baseq[lower_baseq][metric]:
                        violations.append(f"raising baseQ increased {metric}")
                    evaluated += 1
                    baseq_checks[by_baseq[lower_baseq]["track"]] += 1
    by_stage = {
        tuple(row[field] for field in (
            "scope", "reference_id", "region_id", "track", "minimum_mapq",
            "minimum_base_quality", "unit", "window_bp",
        )) + (row["stage"],): row
        for row in measured_rows
    }
    for key, row in by_stage.items():
        if row["stage"] in {"POST_COORDINATE_EXCLUSION", "POST_UMI"}:
            pre = by_stage.get(key[:-1] + ("PRE_DEDUP",))
            if pre:
                for metric in monotonic_metrics:
                    if row[metric] > pre[metric]:
                        violations.append(f"post-ablation {metric} exceeds pre-dedup {metric}")
                    evaluated += 1
    by_unit = {
        tuple(row[field] for field in (
            "scope", "reference_id", "region_id", "track", "minimum_mapq",
            "minimum_base_quality", "stage", "window_bp",
        )) + (row["unit"],): row
        for row in measured_rows
    }
    for key, row in by_unit.items():
        if row["unit"] == "TEMPLATE":
            read_row = by_unit.get(key[:-1] + ("READ",))
            if read_row:
                for metric in monotonic_metrics:
                    if row[metric] > read_row[metric]:
                        violations.append(f"template {metric} exceeds read {metric}")
                    evaluated += 1
    cross_cells: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in coverage:
        if row["minimum_mapq"] != 0:
            continue
        key = tuple(row[field] for field in (
            "scope", "reference_id", "region_id", "minimum_base_quality", "unit", "stage", "window_bp",
        ))
        cross_cells[key][row["track"]] = row
    cross_evaluated = 0
    cross_not_measured = 0
    for tracks in cross_cells.values():
        if set(tracks) != {"unique", "all_eligible"}:
            continue
        unique_row, all_row = tracks["unique"], tracks["all_eligible"]
        if unique_row["measurement_state"] != "MEASURED" or all_row["measurement_state"] != "MEASURED":
            cross_not_measured += len(monotonic_metrics)
            continue
        for metric in monotonic_metrics:
            if unique_row[metric] > all_row[metric]:
                violations.append(f"MAPQ-0 cross-track unique exceeds all_eligible for {metric}")
            cross_evaluated += 1
            evaluated += 1
    cross_state = "MEASURED" if cross_evaluated else "NOT_MEASURED"
    cross_reason = (
        "unique <= all_eligible was evaluated where both MAPQ-0 cells were measured; positive MAPQ thresholds are not comparable"
        if cross_evaluated else
        "no pair of MAPQ-0 unique/all_eligible cells was measurable; positive MAPQ thresholds are not comparable"
    )
    details = {
        "within_track_monotonicity": {
            track: {
                "mapq": {
                    "state": "MEASURED" if mapq_checks[track] else "NOT_APPLICABLE",
                    "evaluated_checks": mapq_checks[track],
                    "reason": None if mapq_checks[track] else "fewer than two MAPQ levels were measurable",
                },
                "baseq": {
                    "state": "MEASURED" if baseq_checks[track] else "NOT_APPLICABLE",
                    "evaluated_checks": baseq_checks[track],
                    "reason": None if baseq_checks[track] else "fewer than two baseQ levels were measurable",
                },
            }
            for track in ("unique", "all_eligible")
        },
        "cross_track_unique_le_all_eligible": {
            "state": cross_state,
            "scope": "MINIMUM_MAPQ_ZERO_WHEN_BOTH_CELLS_MEASURED",
            "evaluated_checks": cross_evaluated,
            "not_measured_checks": cross_not_measured,
            "positive_thresholds": {
                "state": "NOT_APPLICABLE",
                "reason": "unique uses default-pass MAPQ while all_eligible uses per-placement -a MAPQ",
            },
            "reason": cross_reason,
        },
    }
    return sorted(set(violations)), evaluated, details


def coverage_invariant_state(coverage: list[dict]) -> tuple[str, str | None, int, int]:
    measured = sum(row["measurement_state"] == "MEASURED" for row in coverage)
    not_measured = sum(row["measurement_state"] == "NOT_MEASURED" for row in coverage)
    if not measured:
        return "NOT_MEASURED", "no coverage cells were measurable; coverage invariants were not evaluated", 0, not_measured
    if not_measured:
        return "MEASURED", "only MEASURED cells entered applicable invariants", measured, not_measured
    return "MEASURED", None, measured, 0


def coverage_aggregate(rows: list[dict]) -> dict:
    states = Counter(row["measurement_state"] for row in rows)
    total = len(rows)
    measured = states["MEASURED"]
    if measured:
        state = "MEASURED"
        completeness = "COMPLETE" if measured == total else "PARTIAL"
    elif states["NOT_MEASURED"]:
        state, completeness = "NOT_MEASURED", "NONE"
    elif states["NOT_APPLICABLE"]:
        state, completeness = "NOT_APPLICABLE", "NONE"
    else:
        state, completeness = "UNDEFINED", "NONE"
    return {
        "state": state,
        "completeness": completeness,
        "cell_state_counts": dict(sorted(states.items())),
        "measured_cell_count": measured,
        "total_cell_count": total,
        "measured_cell_fraction": measured / total if total else None,
        "cells_with_unknown_mapq": sum(
            isinstance(row.get("unknown_mapq_count"), int) and row["unknown_mapq_count"] > 0
            for row in rows
        ),
        "maximum_unknown_mapq_count_per_cell": max(
            (row["unknown_mapq_count"] for row in rows if isinstance(row.get("unknown_mapq_count"), int)),
            default=None,
        ),
    }


def template_pairing_summary(rows: list[dict]) -> dict:
    invalid = 0
    filtered = 0
    reasons: Counter[str] = Counter()
    seen_cells: set[tuple] = set()
    for row in rows:
        if row.get("unit") != "TEMPLATE":
            continue
        cell_key = (
            row.get("scope"), row.get("reference_id"), row.get("region_id"),
            row.get("track"), row.get("minimum_mapq"), row.get("minimum_base_quality"),
            row.get("stage"),
        )
        if cell_key in seen_cells:
            continue
        seen_cells.add(cell_key)
        count = row.get("pairing_invalid_pnext_count")
        if isinstance(count, int):
            invalid += count
        count = row.get("pairing_filtered_mate_count")
        if isinstance(count, int):
            filtered += count
            reasons_json = row.get("pairing_filtered_mate_reasons_json")
            if isinstance(reasons_json, str) and reasons_json:
                try:
                    parsed = json.loads(reasons_json)
                except (TypeError, ValueError):
                    parsed = {}
                if isinstance(parsed, dict):
                    for cause, occurrences in parsed.items():
                        if isinstance(occurrences, int) and occurrences > 0:
                            reasons[cause] += occurrences
    return {
        "template_cell_count": len(seen_cells),
        "invalid_pnext_count": invalid,
        "filtered_mate_count": filtered,
        "filtered_mate_reasons": dict(sorted(reasons.items())) if reasons else None,
    }


def executable_record(name: str) -> dict:
    executable = shutil.which(name)
    if not executable:
        return {"executable": "UNAVAILABLE", "version": "UNAVAILABLE", "sha256": "UNAVAILABLE"}
    args = [name, "--version"]
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    lines = (result.stdout or result.stderr).splitlines()
    return {
        "executable": str(Path(executable).resolve()),
        "version": lines[0].strip() if lines else "UNKNOWN",
        "sha256": sha256_file(executable),
    }


def index_components(prefix: str | Path) -> dict[str, dict]:
    prefix = str(prefix)
    for extension in ("bt2", "bt2l"):
        paths = {
            component: Path(f"{prefix}.{component}.{extension}")
            for component in ("1", "2", "3", "4", "rev.1", "rev.2")
        }
        if all(path.is_file() and path.stat().st_size for path in paths.values()):
            return {
                component: {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": sha256_file(path)}
                for component, path in paths.items()
            }
    raise ValueError(f"complete Bowtie2 index not found: {prefix}")


def _portable_git(root: Path, arguments: list[str], text: bool = False) -> subprocess.CompletedProcess:
    options = {"capture_output": True, "check": False, "text": text}
    if text:
        options.update({"encoding": "utf-8", "errors": "replace"})
    result = subprocess.run(["git", "-C", str(root), *arguments], **options)
    if result.returncode == 0:
        return result
    marker = root / ".git"
    if not marker.is_file():
        return result
    content = marker.read_text(encoding="utf-8", errors="strict").strip()
    if not content.startswith("gitdir: "):
        return result
    raw_git_dir = content.removeprefix("gitdir: ")
    drive_match = re.fullmatch(r"([A-Za-z]):[\\/](.*)", raw_git_dir)
    if os.name != "nt" and drive_match:
        remainder = drive_match.group(2).replace("\\", "/")
        git_dir = Path("/mnt") / drive_match.group(1).lower() / remainder
    else:
        git_dir = Path(raw_git_dir)
        if not git_dir.is_absolute():
            git_dir = (root / git_dir).resolve()
    return subprocess.run(
        ["git", "--git-dir", str(git_dir), "--work-tree", str(root), *arguments], **options,
    )


def git_head(root: Path) -> str:
    result = _portable_git(root, ["rev-parse", "HEAD"], text=True)
    commit = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("repository commit cannot be resolved; experiment is NOT_REPRODUCIBLE")
    return commit


def source_state(root: Path) -> dict:
    """Identify the source actually executed, not merely the commit it started from.

    HEAD alone does not identify a modified checkout: with uncommitted changes present,
    the commit names an ancestor of the running code rather than the running code. So the
    record also carries whether the working tree is dirty and the SHA-256 of the module
    sources that produced this run, which are the bytes a reviewer needs to reproduce it.
    """
    commit = git_head(root)
    status = _portable_git(root, ["status", "--porcelain"], text=True)
    if status.returncode != 0:
        raise ValueError("repository status cannot be resolved; experiment is NOT_REPRODUCIBLE")
    modified_paths = [line for line in status.stdout.splitlines() if line.strip()]
    module_dir = Path(__file__).resolve().parent
    sources = sorted(
        path for path in module_dir.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sh"} and "__pycache__" not in path.parts
    )
    return {
        "commit": commit,
        "working_tree": "MODIFIED" if modified_paths else "CLEAN",
        "modified_path_count": len(modified_paths),
        "commit_identifies_executed_source": not modified_paths,
        "executing_module_sources": {
            path.relative_to(root).as_posix(): {
                "size": path.stat().st_size, "sha256": sha256_file(path),
            }
            for path in sources
        },
    }


def summarize(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    panel_manifest = load_panel_manifest(args.panel_manifest, args.reference)
    reference_sequences = read_fasta(args.reference)
    reference_lengths = {name: len(sequence) for name, sequence in reference_sequences.items()}
    regions = load_regions(reference_lengths, args.loci)
    primary_records = parse_sam(args.primary_sam)
    placement_records = parse_sam(args.placements_sam)
    validate_alignment_references(primary_records, placement_records, reference_lengths)
    if args.single:
        input_keys = fastq_read_keys(args.single, 0)
        paired = False
        input_paths = {"single": args.single}
    else:
        left, right = fastq_read_keys(args.r1, 1), fastq_read_keys(args.r2, 2)
        left_names, right_names = [key[0] for key in left], [key[0] for key in right]
        if left_names != right_names:
            raise ValueError("paired FASTQ identifiers/order differ")
        input_keys = [item for pair in zip(left, right) for item in pair]
        paired = True
        input_paths = {"r1": args.r1, "r2": args.r2}
    classifications, reconciliation_errors = classify_reads(input_keys, primary_records, placement_records)
    class_rows = classification_rows(args.sample, classifications)
    geometry = geometry_rows(args.sample, input_keys, primary_records, paired)
    stages, stage_states = stage_templates(input_keys, primary_records, args.umi_mode)
    coverage, structured_coverage = build_coverage_rows(
        args.sample, profile, reference_lengths, regions, placement_records, classifications,
        stages, stage_states, reconciliation_errors, paired,
    )
    violations, invariant_checks, invariant_details = validate_invariants(
        input_keys, classifications, geometry, coverage, paired,
    )
    if violations:
        raise ValueError("direct-map invariant violation: " + "; ".join(violations))

    output = Path(args.out_dir)
    write_tsv_atomic(output / "read_classifications.tsv", class_rows, CLASSIFICATION_FIELDS)
    write_tsv_atomic(output / "template_geometry.tsv", geometry, GEOMETRY_FIELDS)
    write_tsv_atomic(output / "coverage_metrics.tsv", coverage, COVERAGE_FIELDS)
    class_counts = Counter(
        item["classification"] for item in classifications.values() if item["measurement_state"] == "MEASURED"
    )
    state_counts = Counter(item["measurement_state"] for item in classifications.values())
    coverage_by_track = {}
    for track in profile["grid"]["tracks"]:
        track_rows = [row for row in coverage if row["track"] == track]
        row_errors = sorted({
            row["reason"] for row in track_rows
            if row["measurement_state"] == "NOT_MEASURED" and row["reason"]
        })
        coverage_by_track[track] = {
            **coverage_aggregate(track_rows),
            "errors": row_errors,
            "template_pairing": template_pairing_summary(track_rows),
        }
    coverage_summary = coverage_aggregate(coverage)
    coverage_summary["by_track"] = coverage_by_track
    coverage_summary["errors"] = sorted({error for item in coverage_by_track.values() for error in item["errors"]})
    coverage_summary["unknown_mapq_count_scope"] = "PER_CELL_AFTER_STAGE_REGION_AND_BASEQ_FILTERS"
    coverage_summary["template_pairing"] = template_pairing_summary(coverage)
    coverage_summary["template_pairing_scope"] = profile["measurement_error_scope"]["template_pairing"]
    coverage_summary["error_scope"] = profile["measurement_error_scope"]
    invariant_state, invariant_reason, measured_cell_count, unmeasured_cell_count = coverage_invariant_state(coverage)
    write_json_atomic(output / "direct_map_metrics.json", {
        "schema_version": METRICS_SCHEMA,
        "contract_versions": OUTPUT_CONTRACTS,
        "governance_state": GOVERNANCE_STATE,
        "diagnostic": DIAGNOSTIC,
        "pipeline_version": PIPELINE_VERSION,
        "sample_id": args.sample, "run_id": args.run_id, "profile_id": profile["profile_id"],
        "profile_revision": profile["profile_revision"],
        "input_reads": len(input_keys), "input_templates": len({name for name, _ in input_keys}),
        "read_classification_counts": {name: class_counts[name] for name in READ_CLASSES},
        "classification_state_counts": dict(sorted(state_counts.items())),
        "orthogonal_counts": {
            name: sum(item.get(name, 0) for item in classifications.values())
            for name in ("secondary", "supplementary", "qc_fail", "mapq_unknown")
        },
        "orthogonal_count_source": profile["track_semantics"]["orthogonal_count_source"],
        "template_geometry": geometry, "stage_states": summarize_stage_states(stages, stage_states),
        "reconciliation": {
            "state": "MEASURED" if not reconciliation_errors else "NOT_MEASURED",
            "errors": reconciliation_errors,
        },
        "coverage_measurement": coverage_summary,
        "coverage": structured_coverage,
        "invariants": {
            "schema_version": INVARIANTS_SCHEMA,
            "state": invariant_state,
            "evaluated_checks": invariant_checks,
            "coverage_cells_measured": measured_cell_count,
            "coverage_cells_not_measured": unmeasured_cell_count,
            **invariant_details,
            "violations": [],
            "reason": invariant_reason,
        },
        # Restored after the reorganization dropped it: the metrics document has to
        # state the boundaries of its own NOT_MEASURED semantics, or a reader takes an
        # unmeasured cell for a measured zero. Every entry below was checked against
        # code that still exists in this module. Two historical entries were NOT
        # restored verbatim: the 20-49 bp "exploratory fragment" caveat, which describes
        # a short-fragment route this module does not implement, and the old claim that
        # the baseline comparison verifies frozen public artifacts, which is no longer
        # true -- that comparison does not run here (see BASELINE_COMPARISON).
        "limitations": [
            "Mapping quantifies support against the selected panel; it is not taxonomic discovery.",
            "Absent support means not recovered by this chain/configuration, not biological absence.",
            "An incomplete panel or missing homologs limits specificity.",
            "Unknown primary MAPQ leaves only the affected unique cells NOT_MEASURED at every threshold, including MAPQ 0; this defensive policy is distinct from placement MAPQ semantics.",
            "Unknown placement MAPQ is included only when minimum_mapq=0 disables thresholding; only positive-threshold all_eligible cells where an unknown placement remains after stage, region and baseQ filters are NOT_MEASURED.",
            "Cross-track unique <= all_eligible is evaluated only at MAPQ 0 where both cells are measured; positive thresholds are NOT_APPLICABLE because the tracks use distinct MAPQ sources.",
            "MAPQ monotonicity for all_eligible is not evaluated when fewer than two MAPQ levels remain measured; baseQ and other applicable invariants remain evaluated.",
            "One primary/all-pass reconciliation error makes every coverage cell NOT_MEASURED; partial reconciliation is not implemented.",
            "Template cells are NOT_MEASURED when paired placements cannot be joined by exact reciprocal PNEXT.",
            "A pairing failure makes the affected TEMPLATE cell NOT_MEASURED; partial template measurement is not implemented within a cell.",
            "The frozen Gene-In 1.1 baseline comparison did not run: its baseline is absent from this repository history, so preservation of those frozen public artifacts is not verified by this run.",
        ],
    })
    normalized_profile = json.loads(Path(args.profile).read_text(encoding="utf-8", errors="strict"))
    write_json_atomic(output / "profile.json", normalized_profile)
    write_json_atomic(output / "panel_manifest.json", panel_manifest)
    repo_root = Path(__file__).resolve().parents[3]
    external_inputs = {"reference": args.reference, "loci": args.loci, **input_paths}
    retained_artifacts = {
        "profile": output / "profile.json", "panel_manifest": output / "panel_manifest.json",
        "primary_bam": args.primary_bam, "placements_bam": args.placements_bam,
    }
    write_json_atomic(output / "provenance.json", {
        "schema_version": "experimental-direct-map-provenance-v2",
        "contract_versions": OUTPUT_CONTRACTS,
        "governance_state": GOVERNANCE_STATE,
        "diagnostic": DIAGNOSTIC,
        "pipeline_version": PIPELINE_VERSION,
        "profile_id": profile["profile_id"], "profile_revision": profile["profile_revision"],
        "profile_compatibility": profile["profile_compatibility"],
        "baseline_comparison": BASELINE_COMPARISON,
        "source_state": source_state(repo_root),
        "commit": git_head(repo_root),
        "sample_id": args.sample, "run_id": args.run_id,
        "seeds": {"bowtie2": profile["aligner"]["seed"], "summarizer": "NOT_APPLICABLE"},
        "commands": {"primary": args.primary_command, "placements": args.placements_command},
        "parameters": {
            "umi_mode": args.umi_mode, "paired": paired, "grid": profile["grid"],
            "track_semantics": profile["track_semantics"],
            "measurement_error_scope": profile["measurement_error_scope"],
        },
        "external_inputs": {
            name: {"path": str(Path(path).resolve()), "size": Path(path).stat().st_size, "sha256": sha256_file(path)}
            for name, path in external_inputs.items()
        },
        "retained_artifacts": {
            name: {"path": Path(path).name, "path_kind": "RUN_RELATIVE", "size": Path(path).stat().st_size,
                   "sha256": sha256_file(path)}
            for name, path in retained_artifacts.items()
        },
        "intermediates": {
            "primary_sam": {"retained": False, "represented_by": "primary.bam"},
            "placements_sam": {"retained": False, "represented_by": "placements.bam"},
        },
        "bowtie2_index": index_components(args.index),
        "tools": {name: executable_record(name) for name in ("python3", "bowtie2", "bowtie2-build", "samtools")},
    })


def validate_contract_identity(profile: dict, metrics: dict, provenance: dict, coverage_fieldnames: list[str]) -> None:
    if profile.get("schema_version") != PROFILE_SCHEMA or profile.get("output_contracts") != OUTPUT_CONTRACTS:
        raise ValueError("retained profile uses an incompatible output contract")
    if metrics.get("schema_version") != METRICS_SCHEMA or metrics.get("contract_versions") != OUTPUT_CONTRACTS:
        raise ValueError("retained metrics use an incompatible schema or output contract")
    invariants = metrics.get("invariants")
    if not isinstance(invariants, dict) or invariants.get("schema_version") != INVARIANTS_SCHEMA:
        raise ValueError("retained invariants use an incompatible schema")
    if provenance.get("contract_versions") != OUTPUT_CONTRACTS:
        raise ValueError("retained provenance does not identify the current output contracts")
    if coverage_fieldnames != COVERAGE_FIELDS:
        raise ValueError("coverage TSV uses an incompatible schema")


def validate_output(directory: Path) -> None:
    required = {
        "primary.bam", "primary.bam.bai", "placements.bam", "placements.bam.bai",
        "read_classifications.tsv", "template_geometry.tsv", "coverage_metrics.tsv",
        "direct_map_metrics.json", "provenance.json", "profile.json", "panel_manifest.json",
        "bowtie2.primary.log", "bowtie2.placements.log",
    }
    missing = sorted(name for name in required if not (directory / name).is_file() or not (directory / name).stat().st_size)
    if missing:
        raise ValueError("missing experimental direct-map artifacts: " + ", ".join(missing))
    for path in directory.rglob("*"):
        if path.is_file() and (path.name.startswith(".") or path.name.endswith(".tmp")):
            raise ValueError(f"temporary artifact remains: {path.name}")
    metrics = json.loads((directory / "direct_map_metrics.json").read_text(encoding="utf-8"))
    profile = load_profile(directory / "profile.json")
    provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    expected_identity = (profile["profile_id"], profile["profile_revision"], profile["pipeline_version"])
    if (
        (metrics.get("profile_id"), metrics.get("profile_revision"), metrics.get("pipeline_version")) != expected_identity or
        (provenance.get("profile_id"), provenance.get("profile_revision"), provenance.get("pipeline_version")) != expected_identity
    ):
        raise ValueError("retained metrics/provenance do not match the v1.2 profile and pipeline identity")
    panel = json.loads((directory / "panel_manifest.json").read_text(encoding="utf-8"))
    if panel.get("schema_version") != "experimental-direct-map-panel-v1":
        raise ValueError("retained panel manifest schema is invalid")
    expected_rows = (
        len(profile["grid"]["tracks"]) * len(profile["grid"]["mapq"]) *
        len(profile["grid"]["baseq"]) * len(profile["grid"]["units"]) *
        len(profile["grid"]["stages"]) * len(profile["grid"]["windows_bp"])
    )
    with (directory / "coverage_metrics.tsv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        coverage_fieldnames = reader.fieldnames or []
    validate_contract_identity(profile, metrics, provenance, coverage_fieldnames)
    if any(row.get("schema_version") != COVERAGE_SCHEMA for row in rows):
        raise ValueError("coverage TSV contains a row from an incompatible schema")
    region_count = len({(row["scope"], row["reference_id"], row["region_id"]) for row in rows})
    if len(rows) != expected_rows * region_count:
        raise ValueError("coverage grid is incomplete")
    if any(row["measurement_state"] not in MEASUREMENT_STATES for row in rows):
        raise ValueError("coverage grid contains an invalid measurement state")


def finalize(args: argparse.Namespace) -> None:
    staging, final = Path(args.staging), Path(args.final)
    if not staging.is_dir() or staging.name != args.run_id or final.name != args.run_id:
        raise ValueError("staging/final directories must exist under the requested run_id")
    if final.exists():
        raise ValueError("final experimental run already exists")
    if (staging / "SUCCESS.json").exists() or (staging / "artifact_manifest.json").exists():
        raise ValueError("staging already contains commit metadata and cannot be reused")
    final.parent.mkdir(parents=True, exist_ok=True)
    if staging.stat().st_dev != final.parent.stat().st_dev:
        raise ValueError("staging and final directory must be on the same filesystem")
    validate_output(staging)
    manifest = build_artifact_manifest(staging)
    # The PERSISTED document must satisfy the shared closed schema
    # ({schema_version, files}) that validate_artifact_manifest() enforces across
    # the whole Evidence system, so direct-map no longer appends its own
    # `direct_map_contract_versions` key here. Appending it made every finalize()
    # write a manifest that failed to revalidate once reloaded from disk, leaving
    # this the only producer in the system whose manifest the shared validator
    # rejects. The contract cross-identification is preserved -- identically -- in
    # SUCCESS.json and provenance.json, and both are bound to this manifest by the
    # hash chain: SUCCESS anchors the manifest's SHA-256 and the manifest anchors
    # every artifact's SHA-256, provenance.json included.
    manifest_errors = validate_artifact_manifest(staging, manifest)
    if manifest_errors:
        raise ValueError("artifact manifest validation failed: " + "; ".join(manifest_errors))
    write_json_atomic(staging / "artifact_manifest.json", manifest)
    # Fail closed on the guarantee itself rather than on the in-memory dict: the
    # document that consumers read is the one on disk.
    persisted_manifest = json.loads((staging / "artifact_manifest.json").read_text(encoding="utf-8"))
    persisted_errors = validate_artifact_manifest(staging, persisted_manifest)
    if persisted_errors:
        raise ValueError("persisted artifact manifest is invalid: " + "; ".join(persisted_errors))
    success = {
        "schema_version": "experimental-direct-map-success-v2",
        "contract_versions": OUTPUT_CONTRACTS,
        "governance_state": GOVERNANCE_STATE,
        "diagnostic": DIAGNOSTIC,
        "pipeline_version": PIPELINE_VERSION,
        "run_id": args.run_id, "status": "done", "completed_at": datetime.now(timezone.utc).isoformat(),
        "artifact_count": len(manifest["files"]),
        "artifact_manifest_sha256": sha256_file(staging / "artifact_manifest.json"),
    }
    write_json_atomic(staging / "SUCCESS.json", success)
    fsync_directory(staging)
    os.replace(staging, final)
    fsync_directory(final.parent)
    print(final)


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct mapping metrics with reproducible artifacts")
    sub = parser.add_subparsers(dest="command", required=True)
    validate_profile_parser = sub.add_parser("validate-profile")
    validate_profile_parser.add_argument("--profile", required=True)
    validate_panel_parser = sub.add_parser("validate-panel")
    validate_panel_parser.add_argument("--manifest", required=True)
    validate_panel_parser.add_argument("--reference", required=True)
    summarize_parser = sub.add_parser("summarize")
    for name in (
        "profile", "sample", "run-id", "reference", "index", "loci", "primary-sam",
        "placements-sam", "primary-bam", "placements-bam", "out-dir",
    ):
        summarize_parser.add_argument(f"--{name}", required=True)
    summarize_parser.add_argument("--r1")
    summarize_parser.add_argument("--r2")
    summarize_parser.add_argument("--single")
    summarize_parser.add_argument("--panel-manifest", required=True)
    summarize_parser.add_argument("--umi-mode", choices=["none", "read_name", "sam_tag"], default="none")
    summarize_parser.add_argument("--primary-command", required=True)
    summarize_parser.add_argument("--placements-command", required=True)
    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--staging", required=True)
    finalize_parser.add_argument("--final", required=True)
    finalize_parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "validate-profile":
        profile = load_profile(args.profile)
        print(json.dumps(profile, sort_keys=True))
    elif args.command == "validate-panel":
        manifest = load_panel_manifest(args.manifest, args.reference)
        print(json.dumps(manifest, sort_keys=True))
    elif args.command == "summarize":
        if bool(args.single) == bool(args.r1 or args.r2):
            parser.error("summarize requires --single or both --r1/--r2")
        if not args.single and not (args.r1 and args.r2):
            parser.error("paired summarization requires both --r1 and --r2")
        summarize(args)
    else:
        finalize(args)


if __name__ == "__main__":
    main()
