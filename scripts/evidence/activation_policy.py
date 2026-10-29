#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .evidence_profile import canonical_sha256, default_profiles_path, load_profile
except ImportError:
    from evidence_profile import canonical_sha256, default_profiles_path, load_profile


POLICY_IDENTITY_FIELDS = (
    "profile_id",
    "profile_version",
    "profile_sha256",
    "activation_record_id",
    "activation_record_sha256",
)
ACTIVATION_FIELDS = {
    "schema_version", "activation_record_id", "status", "target_profile",
}
TARGET_PROFILE_FIELDS = {"profile_id", "profile_version", "expected_profile_sha256"}


def default_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "evidence_activation.json"


def _canonical_sha256(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key not in {"source", "sha256", "activation_record_sha256"}}
    return canonical_sha256(payload)


def _require_exact_fields(value: dict, expected: set[str], context: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise ValueError(f"{context} missing fields: " + ", ".join(sorted(missing)))
    if unknown:
        raise ValueError(f"{context} has unknown fields: " + ", ".join(sorted(unknown)))


def _validate_digest(value: object, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{context} must be a lowercase SHA-256")
    return value


def _load_activation_record(path: str | Path) -> dict:
    source = Path(path)
    with source.open("r", encoding="utf-8", errors="strict") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("activation record must be an object")
    _require_exact_fields(value, ACTIVATION_FIELDS, "activation record")
    if value["schema_version"] != "2.0":
        raise ValueError("activation record requires schema_version 2.0")
    for field in ("activation_record_id",):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"activation record {field} is required")
    if value["status"] != "ACTIVE":
        raise ValueError("activation record is not ACTIVE")
    target = value["target_profile"]
    if not isinstance(target, dict):
        raise ValueError("activation target_profile must be an object")
    _require_exact_fields(target, TARGET_PROFILE_FIELDS, "activation target_profile")
    for field in ("profile_id", "profile_version"):
        if not isinstance(target[field], str) or not target[field].strip():
            raise ValueError(f"activation target_profile {field} is required")
    _validate_digest(target["expected_profile_sha256"], "activation expected_profile_sha256")
    return {
        **value,
        "source": str(source.resolve()),
        "activation_record_sha256": _canonical_sha256(value),
    }


def _resolve_activation_policy(
    activation_path: str | Path,
    *,
    profiles_path: str | Path | None = None,
) -> dict:
    activation = _load_activation_record(activation_path)
    target = activation["target_profile"]
    profile = load_profile(target["profile_id"], profiles_path or default_profiles_path())
    if profile["profile_version"] != target["profile_version"]:
        raise ValueError("activation profile_version does not match the selected profile")
    if profile["profile_sha256"] != target["expected_profile_sha256"]:
        raise ValueError("activation expected_profile_sha256 does not match the selected profile")
    return {
        **profile,
        "activation_record_id": activation["activation_record_id"],
        "activation_record_sha256": activation["activation_record_sha256"],
        "activation_context": "GENERAL",
        "activation_source": activation["source"],
    }


def load_public_activation_policy(
    path: str | Path | None = None,
    *,
    profiles_path: str | Path | None = None,
) -> dict:
    return _resolve_activation_policy(path or default_path(), profiles_path=profiles_path)


def load_activation_policy(path: str | Path | None = None) -> dict:
    """Public-only loader used by public read paths."""
    return load_public_activation_policy(path)


def load_experimental_activation_policy(
    path: str | Path,
    *,
    profiles_path: str | Path | None = None,
) -> dict:
    return _resolve_activation_policy(path, profiles_path=profiles_path)


def policy_identity(policy: dict) -> dict:
    if not isinstance(policy, dict):
        raise ValueError("activation policy must be an object")
    identity = {field: policy.get(field) for field in POLICY_IDENTITY_FIELDS}
    return validate_policy_identity(identity, context="activation policy")


def validate_policy_identity(
    value: dict,
    *,
    expected: dict | None = None,
    context: str = "artifact",
) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    missing = set(POLICY_IDENTITY_FIELDS) - set(value)
    if missing:
        raise ValueError(f"{context} missing policy identity fields: " + ", ".join(sorted(missing)))
    for field in ("profile_id", "profile_version", "activation_record_id"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"{context} {field} is required")
    _validate_digest(value["profile_sha256"], f"{context} profile_sha256")
    _validate_digest(value["activation_record_sha256"], f"{context} activation_record_sha256")
    identity = {field: value[field] for field in POLICY_IDENTITY_FIELDS}
    if expected is not None:
        expected_identity = {field: expected.get(field) for field in POLICY_IDENTITY_FIELDS}
        if identity != expected_identity:
            raise ValueError(f"{context} policy identity does not match the active policy")
    return identity


def conclusion_for(policy: dict, analysis_outcome: str) -> str:
    if analysis_outcome not in {
        "EVIDENCE_RECOVERED", "CANDIDATES_FOR_REVIEW", "NO_EVIDENCE_RECOVERED", "NOT_EVALUABLE",
    }:
        raise ValueError(f"unsupported analysis outcome: {analysis_outcome}")
    return analysis_outcome


def _field_value(value: dict, field: str):
    current = value
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(field)
        current = current[part]
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and inspect an Evidence V2 activation")
    subparsers = parser.add_subparsers(dest="context", required=True)
    public = subparsers.add_parser("public", help="validate the active analysis configuration")
    public.add_argument("--activation", "--policy", dest="activation", type=Path, default=default_path())
    public.add_argument("--profiles", type=Path, default=default_profiles_path())
    public.add_argument("--field")
    experimental = subparsers.add_parser("experimental", help="validate an alternate activation")
    experimental.add_argument("--activation", "--policy", dest="activation", type=Path, required=True)
    experimental.add_argument("--profiles", type=Path, required=True)
    experimental.add_argument("--field")
    args = parser.parse_args()
    if args.context == "public":
        value = load_public_activation_policy(args.activation, profiles_path=args.profiles)
    else:
        value = load_experimental_activation_policy(
            args.activation,
            profiles_path=args.profiles,
        )
    if args.field:
        field = _field_value(value, args.field)
        print(str(field).lower() if isinstance(field, bool) else field)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
