"""Build isolated experimental Evidence policies for Validation runs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

EXPERIMENTAL_PROFILE_ID = "validation-analysis"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def baseline_thresholds(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or _repo_root()
    import sys

    evidence_dir = root / "scripts" / "evidence"
    if str(evidence_dir) not in sys.path:
        sys.path.insert(0, str(evidence_dir))
    from activation_policy import load_public_activation_policy

    return copy.deepcopy(load_public_activation_policy(root / "config" / "evidence_activation.json")["thresholds"])


def apply_parameters(thresholds: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(thresholds)
    mapping = {
        "blast.short_max_bp": ("blast", "short_max_bp"),
        "blast.dual_mode_min_bp": ("blast", "dual_mode_min_bp"),
        "blast.dual_mode_max_bp": ("blast", "dual_mode_max_bp"),
        "locus.minimum_candidate_bp": ("locus", "minimum_candidate_bp"),
        "locus.gap_bp": ("locus", "gap_bp"),
        "specificity.minimum_delta_bitscore": ("specificity", "minimum_delta_bitscore"),
        "specificity.maximum_qcov_difference_pp": ("specificity", "maximum_qcov_difference_pp"),
        "support.minimum_unique_templates": ("support", "minimum_unique_templates"),
        "support.minimum_mapq": ("support", "minimum_mapq"),
    }
    for key, value in parameters.items():
        if key not in mapping:
            continue
        section, field = mapping[key]
        updated[section][field] = value
    return updated


def build_experimental_catalog(thresholds: dict[str, Any], *, parameter_set_id: str) -> dict[str, Any]:
    root = _repo_root()
    public_catalog = json.loads((root / "config" / "evidence_profiles.json").read_text(encoding="utf-8"))
    profile = copy.deepcopy(public_catalog["profiles"]["open-analysis"])
    profile.update(
        {
            "profile_id": EXPERIMENTAL_PROFILE_ID,
            "profile_version": f"validation-{parameter_set_id}",
            "scientific_role": "GENERAL",
            "shadow_mode": False,
            "thresholds": thresholds,
            "presentation": {
                "reported_conclusion": "ANALYSIS_RESULT",
                "required_caveats": [],
            },
        }
    )
    import sys

    evidence_dir = root / "scripts" / "evidence"
    if str(evidence_dir) not in sys.path:
        sys.path.insert(0, str(evidence_dir))
    from evidence_profile import canonical_sha256, validate_profile

    validate_profile(profile, catalog_id=EXPERIMENTAL_PROFILE_ID)
    catalog = {"schema_version": "1.0", "profiles": {EXPERIMENTAL_PROFILE_ID: profile}}
    digest = canonical_sha256(profile)
    return catalog, digest


def build_experimental_activation(profile_digest: str, *, parameter_set_id: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "activation_record_id": f"ACT-VALIDATION-{parameter_set_id}",
        "status": "ACTIVE",
        "target_profile": {
            "profile_id": EXPERIMENTAL_PROFILE_ID,
            "profile_version": f"validation-{parameter_set_id}",
            "expected_profile_sha256": profile_digest,
        },
    }


def materialize_experimental_policy(
    *,
    parameters: dict[str, Any],
    parameter_set_id: str,
    out_dir: Path,
) -> dict[str, Path]:
    thresholds = apply_parameters(baseline_thresholds(), parameters)
    catalog, digest = build_experimental_catalog(thresholds, parameter_set_id=parameter_set_id)
    activation = build_experimental_activation(digest, parameter_set_id=parameter_set_id)
    profiles_path = out_dir / "experimental_profiles.json"
    activation_path = out_dir / "experimental_activation.json"
    profiles_path.parent.mkdir(parents=True, exist_ok=True)
    profiles_path.write_text(json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    activation_path.write_text(json.dumps(activation, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"profiles": profiles_path, "activation": activation_path, "thresholds": thresholds}


def load_experimental_policy(paths: dict[str, Path]) -> dict[str, Any]:
    import sys

    root = _repo_root()
    evidence_dir = root / "scripts" / "evidence"
    if str(evidence_dir) not in sys.path:
        sys.path.insert(0, str(evidence_dir))
    from activation_policy import load_experimental_activation_policy

    return load_experimental_activation_policy(
        paths["activation"],
        profiles_path=paths["profiles"],
    )
