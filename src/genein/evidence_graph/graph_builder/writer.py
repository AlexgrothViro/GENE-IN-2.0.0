"""5. Writer — staging único, promoção atômica, sem apagar pacote válido."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from genein.evidence_graph.graph_builder.parse import (
    HSP_EVIDENCE_COLUMNS,
    MAPPER_VERSION,
    TEMPLATE_LINEAGE_COLUMNS,
    sha256_file,
    write_tsv,
)
from genein.evidence_graph.graph_builder.types import BuildRequest, BuildResult, MapperOutput


class DestinationExistsError(ValueError):
    """Destino final já existe — pacote válido nunca é apagado."""


class StagingConflictError(ValueError):
    """Staging concorrente já presente no mesmo filesystem."""


def assert_outside_pipeline(output_root: Path, run_dir: Path) -> None:
    """Recusa output_root dentro do run_dir ou da área results/evidence do pipeline."""
    output_root = output_root.resolve()
    run_dir = run_dir.resolve()
    try:
        output_root.relative_to(run_dir)
        raise ValueError(f"output_root {output_root} não pode ficar dentro de run_dir {run_dir}")
    except ValueError as exc:
        if "não pode ficar dentro" in str(exc):
            raise
    parts = output_root.parts
    if "results" in parts:
        idx = parts.index("results")
        if idx + 1 < len(parts) and parts[idx + 1] == "evidence":
            raise ValueError(
                f"output_root {output_root} intersecta área do pipeline (results/evidence)"
            )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _build_manifest(directory: Path) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative in {"SUCCESS.json", "artifact_manifest.json"} or path.name.startswith("."):
            continue
        files[relative] = {"size": path.stat().st_size, "sha256": sha256_file(path)}
    return {"schema_version": "1.0", "files": files}


def _copy_or_header_sidecar(
    *,
    staging_dir: Path,
    run_dir: Path,
    digests: dict[str, dict[str, Any]],
    name: str,
    columns: tuple[str, ...],
    scope_notes: list[str],
) -> None:
    source_path = run_dir / name
    dest = staging_dir / name
    if name in digests and source_path.is_file():
        shutil.copy2(source_path, dest)
        actual = sha256_file(dest)
        expected = digests[name].get("sha256", "")
        expected_hex = expected[7:] if str(expected).startswith("sha256:") else expected
        if actual != expected_hex:
            raise ValueError(f"digest do sidecar divergente após cópia: {name}")
        return
    write_tsv(dest, columns, [])
    scope_notes.append(
        f"sidecar histórico ausente: {name} escrito somente com cabeçalho (abstenção)"
    )


def write(
    request: BuildRequest,
    graph: dict[str, Any],
    report: dict[str, Any],
    mapper_output: MapperOutput | None = None,
    *,
    source_digests: dict[str, dict[str, Any]] | None = None,
    mapper_source_version: str | None = None,
) -> BuildResult:
    """Grava em staging; só promove com SUCCESS se o grafo for válido."""
    assert_outside_pipeline(request.output_root, request.run_dir)

    graph_id = graph.get("graph_id", "G-unknown")
    final_dir = request.output_root / graph_id
    staging_dir = request.output_root / f".staging-{graph_id}"

    if final_dir.exists():
        raise DestinationExistsError(
            f"destino já existe e não será sobrescrito: {final_dir}"
        )
    if staging_dir.exists():
        raise StagingConflictError(
            f"staging concorrente presente: {staging_dir}"
        )

    request.output_root.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=False, exist_ok=False)

    scope_notes = list(mapper_output.scope_notes) if mapper_output else []
    digests = source_digests or {}

    graph_path = staging_dir / "evidence_graph.json"
    _write_json(graph_path, graph)

    _copy_or_header_sidecar(
        staging_dir=staging_dir,
        run_dir=request.run_dir,
        digests=digests,
        name="hsp_evidence.tsv",
        columns=HSP_EVIDENCE_COLUMNS,
        scope_notes=scope_notes,
    )
    _copy_or_header_sidecar(
        staging_dir=staging_dir,
        run_dir=request.run_dir,
        digests=digests,
        name="template_lineage.tsv",
        columns=TEMPLATE_LINEAGE_COLUMNS,
        scope_notes=scope_notes,
    )
    if scope_notes:
        (staging_dir / "mapper_scope_notes.txt").write_text(
            "\n".join(scope_notes) + "\n", encoding="utf-8"
        )

    validation_path = staging_dir / "validation_report.json"
    _write_json(validation_path, report)

    if not report.get("valid"):
        # Grafo inválido permanece no staging, sem SUCCESS.json.
        raise ValueError(
            f"grafo {graph_id} inválido; artefatos mantidos somente em staging"
        )

    manifest = _build_manifest(staging_dir)
    _write_json(staging_dir / "artifact_manifest.json", manifest)

    success: dict[str, Any] = {
        "graph_id": graph_id,
        "status": "done",
        "validated_at": graph.get("created_at"),
        "artifact_manifest_sha256": sha256_file(staging_dir / "artifact_manifest.json"),
        "evidence_graph_sha256": sha256_file(staging_dir / "evidence_graph.json"),
        "source_run_id": request.run_dir.name,
        "mapper_version": MAPPER_VERSION,
    }
    if mapper_source_version is not None:
        success["mapper_source_version"] = mapper_source_version
    _write_json(staging_dir / "SUCCESS.json", success)

    os.replace(staging_dir, final_dir)

    graph_digest = sha256_file(final_dir / "evidence_graph.json")
    return BuildResult(
        graph_id=graph_id,
        graph_dir=final_dir,
        graph_digest=f"sha256:{graph_digest}",
        valid=True,
        report=report,
        mapper_output=mapper_output,
    )
