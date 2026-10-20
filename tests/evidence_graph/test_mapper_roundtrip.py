from __future__ import annotations

import json
from pathlib import Path

from genein.evidence_graph.graph_builder.mapper import map_all
from genein.evidence_graph.graph_builder.pipeline import build
from genein.evidence_graph.graph_builder.reader import read
from genein.evidence_graph.graph_builder.types import BuildRequest
from genein.evidence_graph.graph_builder.validator import validate
from genein.evidence_graph.graph_builder.parse import sha256_file
from tests.evidence_graph.mapper_fixtures import FIXTURES_ROOT, PRODUCTION_CATALOG, materialize_run

CATALOG = PRODUCTION_CATALOG


def test_roundtrip_preserves_observations(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    request = BuildRequest(
        run_dir=run_dir,
        output_root=tmp_path / "roundtrip-out",
        rule_catalog_path=CATALOG,
    )
    source = read(request)
    before_rows = len(source.tables.get("template_lineage.tsv", []))
    output = map_all(source)
    rs_nodes = [node for node in output.nodes if node["type"] == "ReadSupport"]
    assert len(rs_nodes) == before_rows
    for node in rs_nodes:
        assert node["observation"]["observed"] is True
        assert "raw" in node["observation"]


def test_roundtrip_validator_accepts_factual_graph(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    request = BuildRequest(
        run_dir=run_dir,
        output_root=tmp_path / "roundtrip-val",
        rule_catalog_path=CATALOG,
    )
    source = read(request)
    mapped = map_all(source)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    from genein.evidence_graph.graph_builder.parse import sha256_file as _sha

    artifacts = {
        ref: (meta["sha256"] if str(meta["sha256"]).startswith("sha256:") else f"sha256:{meta['sha256']}")
        for ref, meta in source.digests.items()
    }
    graph = {
        "schema_version": "0.2",
        "graph_id": "G-roundtrip-test",
        "mapper_version": "0.2.2",
        "rule_catalog_version": "rule-catalog:0.1",
        "rule_catalog_digest": f"sha256:{_sha(CATALOG)}",
        "source_manifest_digest": f"sha256:{_sha(run_dir / 'artifact_manifest.json')}",
        "source_artifacts": artifacts,
        "source_run_id": source.run_id,
        "created_at": "2026-08-06T12:00:00Z",
        "nodes": mapped.nodes,
        "edges": mapped.edges,
        "evaluation": [],
    }
    report = validate(graph, catalog)
    assert report["valid"] is True, report


def test_roundtrip_semantic_and_byte_equality(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    result = build(
        BuildRequest(run_dir=run_dir, output_root=tmp_path, rule_catalog_path=CATALOG)
    )
    source = read(
        BuildRequest(run_dir=run_dir, output_root=tmp_path / "unused", rule_catalog_path=CATALOG)
    )
    mapped = map_all(source)
    graph = json.loads((result.graph_dir / "evidence_graph.json").read_text(encoding="utf-8"))
    assert len([n for n in graph["nodes"] if n["type"] == "HSP"]) == len(mapped.hsp_evidence_rows)
    assert len([n for n in graph["nodes"] if n["type"] == "ReadSupport"]) == len(
        mapped.template_lineage_rows
    )
    assert sha256_file(result.graph_dir / "hsp_evidence.tsv") == sha256_file(run_dir / "hsp_evidence.tsv")
    assert sha256_file(result.graph_dir / "template_lineage.tsv") == sha256_file(
        run_dir / "template_lineage.tsv"
    )
