#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROFILE_FIELDS = {
    "profile_id", "profile_version", "status", "scientific_role", "shadow_mode",
    "evidence_ceiling", "allowed_evidence_levels", "diagnostic_language_allowed",
    "analysis_profile_id", "thresholds", "gates", "presentation",
}
GATE_FIELDS = {
    "gate_id", "scope", "allowed_statuses", "required_for_evaluation",
    "required_for_candidate_promotion", "metric_refs",
}
THRESHOLD_KEYS = {
    "blast": {"short_max_bp", "dual_mode_min_bp", "dual_mode_max_bp", "explicit_dust", "soft_masking"},
    "locus": {"gap_bp", "minimum_candidate_bp"},
    "support": {"minimum_unique_templates", "minimum_distinct_starts_shotgun", "minimum_mapq", "minimum_base_quality", "require_proper_pair_shotgun"},
    "specificity": {"minimum_delta_bitscore", "maximum_qcov_difference_pp"},
    "sample_evidence": {"multi_locus_minimum", "multi_locus_total_bp", "genome_breadth_1x", "median_covered_depth", "concentration_window_bp"},
    "controls": {"provisional_sample_to_negative_ratio", "uncontrolled_maximum"},
    "phylogeny": {"minimum_aligned_bp", "minimum_informative_sites", "minimum_references", "maximum_n_fraction", "maximum_gap_fraction"},
}
def default_profiles_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "evidence_profiles.json"


def canonical_sha256(value: dict) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _exact_fields(value: dict, expected: set[str], context: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise ValueError(f"{context} missing fields: " + ", ".join(sorted(missing)))
    if unknown:
        raise ValueError(f"{context} has unknown fields: " + ", ".join(sorted(unknown)))


def validate_thresholds(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("profile thresholds must be an object")
    _exact_fields(data, set(THRESHOLD_KEYS), "profile thresholds")
    for section, keys in THRESHOLD_KEYS.items():
        value = data[section]
        if not isinstance(value, dict):
            raise ValueError(f"profile thresholds.{section} must be an object")
        _exact_fields(value, keys, f"profile thresholds.{section}")

    def number(section: str, key: str, minimum: float, maximum: float | None = None) -> float:
        value = data[section][key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"thresholds.{section}.{key} must be numeric")
        numeric = float(value)
        if numeric < minimum or (maximum is not None and numeric > maximum):
            raise ValueError(f"thresholds.{section}.{key} is outside the allowed range")
        return numeric

    for section, key in (("blast", "explicit_dust"), ("blast", "soft_masking"), ("support", "require_proper_pair_shotgun")):
        if not isinstance(data[section][key], bool):
            raise ValueError(f"thresholds.{section}.{key} must be boolean")
    short = number("blast", "short_max_bp", 1)
    dual_min = number("blast", "dual_mode_min_bp", 1)
    dual_max = number("blast", "dual_mode_max_bp", 1)
    if not short < dual_min <= dual_max:
        raise ValueError("BLAST length boundaries are inconsistent")
    for section, key, low, high in (
        ("locus", "gap_bp", 0, None), ("locus", "minimum_candidate_bp", 1, None),
        ("support", "minimum_unique_templates", 0, None), ("support", "minimum_distinct_starts_shotgun", 0, None),
        ("support", "minimum_mapq", 0, 255), ("support", "minimum_base_quality", 0, 255),
        ("specificity", "minimum_delta_bitscore", 0, None), ("specificity", "maximum_qcov_difference_pp", 0, 100),
        ("sample_evidence", "multi_locus_minimum", 1, None), ("sample_evidence", "multi_locus_total_bp", 1, None),
        ("sample_evidence", "genome_breadth_1x", 0, 1), ("sample_evidence", "median_covered_depth", 0, None),
        ("sample_evidence", "concentration_window_bp", 1, None),
        ("controls", "provisional_sample_to_negative_ratio", 0, None),
        ("phylogeny", "minimum_aligned_bp", 1, None), ("phylogeny", "minimum_informative_sites", 0, None),
        ("phylogeny", "minimum_references", 1, None), ("phylogeny", "maximum_n_fraction", 0, 1),
        ("phylogeny", "maximum_gap_fraction", 0, 1),
    ):
        number(section, key, low, high)
    if not isinstance(data["controls"]["uncontrolled_maximum"], str) or not data["controls"]["uncontrolled_maximum"].strip():
        raise ValueError("thresholds.controls.uncontrolled_maximum must be a non-empty string")
    return data


def validate_profile(profile: object, *, catalog_id: str | None = None) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("evidence profile must be an object")
    _exact_fields(profile, PROFILE_FIELDS, "evidence profile")
    for field in ("profile_id", "profile_version", "analysis_profile_id"):
        if not isinstance(profile[field], str) or not profile[field].strip():
            raise ValueError(f"evidence profile {field} is required")
    if catalog_id is not None and profile["profile_id"] != catalog_id:
        raise ValueError("evidence profile_id does not match its catalog key")
    if profile["status"] != "ACTIVE":
        raise ValueError("evidence profile is not ACTIVE")
    if not isinstance(profile["scientific_role"], str) or not profile["scientific_role"].strip():
        raise ValueError("evidence profile scientific_role is required")
    if not isinstance(profile["shadow_mode"], bool):
        raise ValueError("evidence profile shadow_mode must be boolean")
    if not isinstance(profile["evidence_ceiling"], str) or not profile["evidence_ceiling"].strip():
        raise ValueError("evidence profile evidence_ceiling is required")
    if not isinstance(profile["allowed_evidence_levels"], list) or not all(
        isinstance(level, str) and level for level in profile["allowed_evidence_levels"]
    ):
        raise ValueError("evidence profile allowed_evidence_levels must contain strings")
    if not isinstance(profile["diagnostic_language_allowed"], bool):
        raise ValueError("evidence profile diagnostic_language_allowed must be boolean")
    validate_thresholds(profile["thresholds"])
    gates = profile["gates"]
    if not isinstance(gates, list):
        raise ValueError("evidence profile gates must be a list")
    seen: set[str] = set()
    for gate in gates:
        if not isinstance(gate, dict):
            raise ValueError("evidence profile gate must be an object")
        _exact_fields(gate, GATE_FIELDS, "evidence profile gate")
        gate_id = gate["gate_id"]
        if not isinstance(gate_id, str) or not gate_id or gate_id in seen:
            raise ValueError("evidence profile gate_id is missing or duplicated")
        seen.add(gate_id)
        if gate["scope"] not in {"CANDIDATE", "SAMPLE", "BATCH", "CEILING"}:
            raise ValueError(f"evidence profile gate {gate_id} has invalid scope")
        statuses = gate["allowed_statuses"]
        if not isinstance(statuses, list) or not statuses or not set(statuses) <= {"PASS", "BLOCKED", "NOT_EVALUABLE"}:
            raise ValueError(f"evidence profile gate {gate_id} has invalid statuses")
        for field in ("required_for_evaluation", "required_for_candidate_promotion"):
            if not isinstance(gate[field], bool):
                raise ValueError(f"evidence profile gate {gate_id} {field} must be boolean")
        if not isinstance(gate["metric_refs"], list) or not all(isinstance(item, str) for item in gate["metric_refs"]):
            raise ValueError(f"evidence profile gate {gate_id} metric_refs must be strings")
    presentation = profile["presentation"]
    if not isinstance(presentation, dict):
        raise ValueError("evidence profile presentation must be an object")
    _exact_fields(presentation, {"reported_conclusion", "required_caveats"}, "evidence profile presentation")
    if not isinstance(presentation["reported_conclusion"], str) or not presentation["reported_conclusion"]:
        raise ValueError("evidence profile reported conclusion is required")
    if not isinstance(presentation["required_caveats"], list) or not all(isinstance(item, str) for item in presentation["required_caveats"]):
        raise ValueError("evidence profile required_caveats must contain strings")
    return profile


def load_profile(profile_id: str, path: str | Path | None = None) -> dict:
    source = Path(path) if path else default_profiles_path()
    with source.open("r", encoding="utf-8", errors="strict") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict):
        raise ValueError("evidence profile catalog must be an object")
    _exact_fields(catalog, {"schema_version", "profiles"}, "evidence profile catalog")
    if catalog["schema_version"] != "1.0" or not isinstance(catalog["profiles"], dict):
        raise ValueError("evidence profile catalog requires schema_version 1.0")
    validated = {
        catalog_id: validate_profile(profile, catalog_id=catalog_id)
        for catalog_id, profile in catalog["profiles"].items()
    }
    if profile_id not in validated:
        raise ValueError(f"unknown evidence profile: {profile_id}")
    profile = validated[profile_id]
    return {**profile, "profile_source": str(source.resolve()), "profile_sha256": canonical_sha256(profile)}


def gate_catalog(profile: dict) -> dict[str, dict]:
    return {gate["gate_id"]: gate for gate in profile["gates"]}


def validate_gate_results(profile: dict, gates: object) -> list[dict]:
    if not isinstance(gates, list):
        raise ValueError("promotion_gates must be a list")
    catalog = gate_catalog(profile)
    results: dict[str, dict] = {}
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != {"gate_id", "status", "reason"}:
            raise ValueError("promotion gate must contain gate_id, status, and reason")
        gate_id = gate["gate_id"]
        if gate_id not in catalog:
            raise ValueError(f"unknown promotion gate: {gate_id}")
        if gate_id in results:
            raise ValueError(f"duplicate promotion gate: {gate_id}")
        if gate["status"] not in catalog[gate_id]["allowed_statuses"]:
            raise ValueError(f"invalid status for promotion gate: {gate_id}")
        if not isinstance(gate["reason"], str) or not gate["reason"]:
            raise ValueError(f"promotion gate reason is required: {gate_id}")
        results[gate_id] = gate
    required = {gate_id for gate_id, definition in catalog.items() if definition["required_for_evaluation"]}
    missing = required - set(results)
    if missing:
        raise ValueError("missing required promotion gates: " + ", ".join(sorted(missing)))
    if set(results) != set(catalog):
        raise ValueError("promotion gates do not match the selected profile")
    return gates
