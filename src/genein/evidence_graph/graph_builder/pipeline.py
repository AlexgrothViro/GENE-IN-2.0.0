"""Orquestração dos componentes factuais do Mapper v0.2.2."""
from __future__ import annotations

import json
from pathlib import Path

from genein.evidence_graph.graph_builder.mapper import map_all
from genein.evidence_graph.graph_builder.parse import MAPPER_VERSION, RULE_CATALOG_VERSION, sha256_file, utc_now_iso
from genein.evidence_graph.graph_builder.reader import read
from genein.evidence_graph.graph_builder.types import BuildRequest, BuildResult
from genein.evidence_graph.graph_builder.validator import validate
from genein.evidence_graph.graph_builder.writer import write


def _load_catalog(request: BuildRequest) -> dict:
    return json.loads(request.rule_catalog_path.read_text(encoding="utf-8"))


def _source_artifacts_map(digests: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for source_ref, meta in digests.items():
        raw = meta.get("sha256", "")
        out[source_ref] = raw if str(raw).startswith("sha256:") else f"sha256:{raw}"
    return out


def build(request: BuildRequest) -> BuildResult:
    """Projeta uma execução Evidence V2 promovida em evidence_graph.json derivado."""
    source = read(request)
    mapper_output = map_all(source)
    catalog = _load_catalog(request)

    manifest_path = source.run_dir / "artifact_manifest.json"
    catalog_digest = f"sha256:{sha256_file(request.rule_catalog_path)}"
    success_doc = source.documents.get("SUCCESS.json", {})
    mapper_source_version = success_doc.get("mapper_source_version")

    graph_id = f"G-{source.run_id}"
    graph: dict = {
        "schema_version": "0.2",
        "graph_id": graph_id,
        "mapper_version": MAPPER_VERSION,
        "rule_catalog_version": RULE_CATALOG_VERSION,
        "rule_catalog_digest": catalog_digest,
        "source_manifest_digest": f"sha256:{sha256_file(manifest_path)}",
        "source_artifacts": _source_artifacts_map(source.digests),
        "created_at": utc_now_iso(),
        "source_run_id": source.run_id,
        "nodes": mapper_output.nodes,
        "edges": mapper_output.edges,
        "evaluation": [],
        "mapper_scope_notes": mapper_output.scope_notes,
    }

    report = validate(graph, catalog)
    return write(
        request,
        graph,
        report,
        mapper_output,
        source_digests=source.digests,
        mapper_source_version=mapper_source_version if isinstance(mapper_source_version, str) else None,
    )
