#!/usr/bin/env python3
"""Fast operational checks for the Evidence V2 process.

This intentionally checks only policy resolution and command availability. It
does not hash executables, qualify a Conda environment, or probe tool versions.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

try:
    from .activation_policy import (
        load_experimental_activation_policy, load_public_activation_policy,
        policy_identity,
    )
except ImportError:
    from activation_policy import (
        load_experimental_activation_policy, load_public_activation_policy,
        policy_identity,
    )


def run(
    activation: Path | None,
    profiles: Path | None,
    assembler: str,
    umi_mode: str,
    require_phylogeny: bool,
    required_commands: list[str],
) -> tuple[dict, list[str]]:
    errors: list[str] = []
    report: dict = {
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "policy": None,
        "commands": {},
    }
    try:
        if activation and activation.name != "evidence_activation.json":
            policy = load_experimental_activation_policy(
                activation, profiles_path=profiles,
            )
        else:
            policy = load_public_activation_policy(activation, profiles_path=profiles)
        report["policy"] = policy_identity(policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"política Evidence V2 inválida: {exc}")

    selected = list(required_commands)
    if assembler == "velvet":
        selected.extend(["velveth", "velvetg"])
    elif assembler == "spades":
        selected.append("spades.py")
    elif assembler == "metaspades":
        selected.append("metaspades.py")
    if umi_mode != "none":
        selected.append("umi_tools")
    if require_phylogeny:
        selected.append("iqtree2" if shutil.which("iqtree2") else "iqtree")
    for name in dict.fromkeys(selected):
        path = shutil.which(name)
        report["commands"][name] = {"available": bool(path), "path": path}
        if not path:
            errors.append(f"dependência ausente: {name}")
    report["valid"] = not errors
    report["errors"] = errors
    return report, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight operacional leve da Evidence V2")
    activation = parser.add_mutually_exclusive_group()
    activation.add_argument("--activation-policy", type=Path)
    activation.add_argument("--experimental-activation-policy", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--assembler", choices=["none", "velvet", "spades", "metaspades"], default="none")
    parser.add_argument("--umi-mode", choices=["none", "read_name", "tag"], default="none")
    parser.add_argument("--require-phylogeny", action="store_true")
    parser.add_argument("--require-command", action="append", default=[])
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    report, errors = run(
        args.experimental_activation_policy or args.activation_policy, args.profiles,
        args.assembler, args.umi_mode,
        args.require_phylogeny, args.require_command,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
        )
    if errors:
        for error in errors:
            print(f"[FATAL] {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
