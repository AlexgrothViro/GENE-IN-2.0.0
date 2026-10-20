"""Reproducible parameter-set identity for Validation experiments."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parameter_set_id(parameters: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(parameters).encode("utf-8")).hexdigest()
    return f"ps-{digest[:16]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def expand_grid(grid: dict[str, Any]) -> list[dict[str, Any]]:
    axes = grid.get("axes") or {}
    if not axes:
        return [dict(grid.get("base_parameters") or {})]
    keys = sorted(axes)
    values = [axes[key] for key in keys]
    combinations: list[dict[str, Any]] = []

    def walk(index: int, current: dict[str, Any]) -> None:
        if index == len(keys):
            merged = dict(grid.get("base_parameters") or {})
            merged.update(current)
            combinations.append(merged)
            return
        key = keys[index]
        for item in values[index]:
            walk(index + 1, {**current, key: item})

    walk(0, {})
    return combinations


def materialize_parameter_set(
    *,
    experiment_id: str,
    parameters: dict[str, Any],
    out_dir: Path,
    baseline_commit: str,
    grid_id: str,
) -> dict[str, Any]:
    identity = parameter_set_id(parameters)
    record = {
        "schema_version": "validation-parameter-set-v1",
        "experiment_id": experiment_id,
        "parameter_set_id": identity,
        "grid_id": grid_id,
        "baseline_commit": baseline_commit,
        "parameters": parameters,
    }
    write_json_atomic(out_dir / "parameter_sets" / f"{identity}.json", record)
    return record
