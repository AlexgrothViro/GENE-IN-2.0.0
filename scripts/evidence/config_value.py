#!/usr/bin/env python3
from __future__ import annotations

import argparse

try:
    from .activation_policy import load_public_activation_policy
except ImportError:
    from activation_policy import load_public_activation_policy


def main() -> None:
    parser = argparse.ArgumentParser(description="Read one validated evidence config value")
    parser.add_argument("--activation-policy")
    parser.add_argument("--profiles")
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    policy = load_public_activation_policy(
        args.activation_policy,
        profiles_path=args.profiles,
    )
    value = policy["thresholds"]
    for part in args.key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(args.key)
        value = value[part]
    if isinstance(value, bool):
        print("true" if value else "false")
    elif isinstance(value, (str, int, float)):
        print(value)
    else:
        raise ValueError("requested config key is not scalar")


if __name__ == "__main__":
    main()
