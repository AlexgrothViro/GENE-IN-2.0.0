"""Utilitários de fixture para testes do Mapper."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from genein.evidence_graph.graph_builder.parse import sha256_file

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "mapper"
REPO_ROOT = Path(__file__).parents[2]
ALPHA2 = REPO_ROOT / "scripts" / "tests" / "evidence" / "fixtures" / "alpha2_complete"
from genein.evidence_graph.resources import DEFAULT_CATALOG as PRODUCTION_CATALOG


def write_manifest(run_dir: Path) -> dict:
    files: dict[str, dict[str, str | int]] = {}
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(run_dir).as_posix()
        if relative in {"SUCCESS.json", "artifact_manifest.json"}:
            continue
        files[relative] = {"size": path.stat().st_size, "sha256": sha256_file(path)}
    manifest = {"schema_version": "1.0", "files": files}
    (run_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def write_success(run_dir: Path, *, base: dict | None = None) -> None:
    sample = json.loads((run_dir / "sample_evidence.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    success: dict = {
        "artifact_count": len(files),
        "artifact_manifest_sha256": sha256_file(run_dir / "artifact_manifest.json"),
        "run_id": sample.get("run_id", run_dir.name),
        "status": "done",
        "validated_at": "2026-08-17T00:00:00Z",
    }
    if base:
        for key in (
            "mapper_source_version",
            "pipeline_version",
            "policy_version",
            "shadow_mode",
            "sample_evidence_sha256",
        ):
            if key in base:
                success[key] = base[key]
    if "sample_evidence_sha256" not in success and (run_dir / "sample_evidence.json").is_file():
        success["sample_evidence_sha256"] = sha256_file(run_dir / "sample_evidence.json")
    (run_dir / "SUCCESS.json").write_text(json.dumps(success, indent=2) + "\n", encoding="utf-8")


def materialize_run(name: str, *, root: Path, extra_files: dict[str, str] | None = None) -> Path:
    src = FIXTURES_ROOT / name
    if not src.is_dir():
        raise FileNotFoundError(src)
    dst = root / "runs" / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    if extra_files:
        for relative, content in extra_files.items():
            path = dst / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    # Drop stale commit metadata before rebuilding.
    (dst / "SUCCESS.json").unlink(missing_ok=True)
    (dst / "artifact_manifest.json").unlink(missing_ok=True)
    write_manifest(dst)
    base = {}
    src_success = src / "SUCCESS.json"
    if src_success.is_file():
        base = json.loads(src_success.read_text(encoding="utf-8"))
    write_success(dst, base=base)
    return dst
