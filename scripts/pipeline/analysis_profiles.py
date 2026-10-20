#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ASSEMBLERS = {"velvet", "spades", "metaspades"}
PLUGIN_KINDS = {"assembly", "candidate_generation", "corroboration", "characterization", "quality_control"}
PLUGIN_STATUSES = {"ACTIVE", "EXPERIMENTAL", "DISABLED"}


def default_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "analysis_profiles.json"


def load_profiles(path: str | Path | None = None) -> dict:
    source = Path(path) if path else default_path()
    with source.open("r", encoding="utf-8", errors="strict") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ValueError("analysis profiles require schema_version 1.0")
    if set(value) != {"schema_version", "default_profile", "plugins", "profiles"}:
        raise ValueError("analysis profile top-level fields are invalid")
    if not isinstance(value["plugins"], list) or not isinstance(value["profiles"], dict):
        raise ValueError("plugins must be a list and profiles must be an object")

    plugin_ids: set[str] = set()
    for plugin in value["plugins"]:
        if not isinstance(plugin, dict):
            raise ValueError("plugin entry must be an object")
        required = {
            "id", "kind", "status", "implementation", "input_contract",
            "output_contract", "evidence_authority", "required_tools",
        }
        if set(plugin) != required:
            raise ValueError(f"plugin fields are invalid: {plugin.get('id', '<unknown>')}")
        plugin_id = plugin["id"]
        if not isinstance(plugin_id, str) or not plugin_id or plugin_id in plugin_ids:
            raise ValueError("plugin id must be unique and non-empty")
        plugin_ids.add(plugin_id)
        if plugin["kind"] not in PLUGIN_KINDS:
            raise ValueError(f"invalid plugin kind: {plugin_id}")
        if plugin["status"] not in PLUGIN_STATUSES:
            raise ValueError(f"invalid plugin status: {plugin_id}")
        if not isinstance(plugin["evidence_authority"], str) or not plugin["evidence_authority"].strip():
            raise ValueError(f"plugin evidence_authority is required: {plugin_id}")
        implementation = Path(plugin["implementation"])
        if implementation.is_absolute() or ".." in implementation.parts:
            raise ValueError(f"plugin implementation must be repository-relative: {plugin_id}")
        if not isinstance(plugin["required_tools"], list) or not all(
            isinstance(item, str) and item for item in plugin["required_tools"]
        ):
            raise ValueError(f"plugin required_tools are invalid: {plugin_id}")

    if value["default_profile"] not in value["profiles"]:
        raise ValueError("default_profile is not defined")
    for profile_id, profile in value["profiles"].items():
        if not isinstance(profile_id, str) or not profile_id:
            raise ValueError("profile id is invalid")
        if not isinstance(profile, dict):
            raise ValueError(f"profile must be an object: {profile_id}")
        required = {
            "status", "scientific_role", "evidence_ceiling", "assembly", "enabled_plugins",
        }
        if set(profile) != required:
            raise ValueError(f"profile fields are invalid: {profile_id}")
        if profile["status"] not in {"ACTIVE", "EXPERIMENTAL", "DISABLED"}:
            raise ValueError(f"profile status is invalid: {profile_id}")
        if not isinstance(profile["scientific_role"], str) or not profile["scientific_role"]:
            raise ValueError(f"profile scientific_role is required: {profile_id}")
        if not isinstance(profile["evidence_ceiling"], str) or not profile["evidence_ceiling"]:
            raise ValueError(f"profile evidence_ceiling is required: {profile_id}")
        enabled = profile["enabled_plugins"]
        if not isinstance(enabled, list) or not enabled or set(enabled) - plugin_ids:
            raise ValueError(f"profile enabled_plugins are invalid: {profile_id}")
        assembly = profile["assembly"]
        expected_assembly = {
            "strategy", "assemblers", "minimum_successful_assemblers",
            "allow_manual_assembler_override", "concordance_policy",
        }
        if not isinstance(assembly, dict) or set(assembly) != expected_assembly:
            raise ValueError(f"profile assembly contract is invalid: {profile_id}")
        if assembly["strategy"] not in {"single", "consensus"}:
            raise ValueError(f"profile assembly strategy is invalid: {profile_id}")
        assemblers = assembly["assemblers"]
        if not isinstance(assemblers, list) or not assemblers or set(assemblers) - ASSEMBLERS:
            raise ValueError(f"profile assemblers are invalid: {profile_id}")
        if len(assemblers) != len(set(assemblers)):
            raise ValueError(f"profile assemblers contain duplicates: {profile_id}")
        minimum = assembly["minimum_successful_assemblers"]
        if isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= len(assemblers):
            raise ValueError(f"profile minimum_successful_assemblers is invalid: {profile_id}")
        if not isinstance(assembly["allow_manual_assembler_override"], bool):
            raise ValueError(f"profile manual override flag is invalid: {profile_id}")
        if assembly["strategy"] == "consensus" and minimum < 2:
            raise ValueError("consensus profile requires at least two successful assemblers")
    return value


def resolve_profile(config: dict, profile_id: str | None) -> tuple[str, dict]:
    selected = profile_id or config["default_profile"]
    try:
        profile = config["profiles"][selected]
    except KeyError as exc:
        raise ValueError(f"unknown analysis profile: {selected}") from exc
    if profile["status"] != "ACTIVE":
        raise ValueError(f"analysis profile is not active: {selected}")
    return selected, profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and resolve Gene-In analysis profiles")
    parser.add_argument("--config", type=Path, default=default_path())
    parser.add_argument("--profile")
    parser.add_argument(
        "--field",
        choices=[
            "profile_id", "strategy", "assemblers", "minimum_successful_assemblers",
            "allow_manual_assembler_override", "concordance_policy", "evidence_ceiling",
        ],
    )
    args = parser.parse_args()
    config = load_profiles(args.config)
    profile_id, profile = resolve_profile(config, args.profile)
    if not args.field:
        print(json.dumps({"profile_id": profile_id, **profile}, ensure_ascii=False, indent=2, sort_keys=True))
        return
    assembly = profile["assembly"]
    fields = {
        "profile_id": profile_id,
        "strategy": assembly["strategy"],
        "assemblers": "\n".join(assembly["assemblers"]),
        "minimum_successful_assemblers": assembly["minimum_successful_assemblers"],
        "allow_manual_assembler_override": assembly["allow_manual_assembler_override"],
        "concordance_policy": assembly["concordance_policy"],
        "evidence_ceiling": profile["evidence_ceiling"],
    }
    result = fields[args.field]
    print(str(result).lower() if isinstance(result, bool) else result)


if __name__ == "__main__":
    main()
