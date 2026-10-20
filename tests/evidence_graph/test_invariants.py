from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from genein.evidence_graph.resources import DEFAULT_SCHEMA

from tests.evidence_graph.fixture_graphs import CATALOG, FIXTURES
from genein.evidence_graph.validator.cli import run
from genein.evidence_graph.validator.evaluator import evaluate_all
from genein.evidence_graph.validator.invariants import expected_scope, validate_invariants

SCHEMA = json.loads(
    (DEFAULT_SCHEMA).read_text(encoding="utf-8")
)

EXPECTED = {
    "F1": {"status": "COHERENT", "codes": set()},
    "F2": {"status": "CONFLICTED", "codes": set()},
    "F3": {"status": "INSUFFICIENT", "codes": set()},
    "F4": {"status": "NOT_EVALUABLE", "codes": {"MISSING_ENDPOINT"}},
    "F5": {"status": "COHERENT", "codes": set(), "lineage_count": 1},
    "F6": {"status": "CONFLICTED", "codes": set(), "has_competes": True, "has_contradicts": False},
    "F7": {"status": "COHERENT", "codes": {"MISSING_ENDPOINT"}, "excludes_remote_branch": True},
    "F8": {"status": "COHERENT", "codes": set(), "has_rejection": True},
    "F9": {"status": "COHERENT", "codes": set(), "excludes_remote_conflict": True},
    "F10": {"status": "CONFLICTED", "codes": set(), "has_conflict_and_exception": True},
}


@pytest.mark.parametrize("fixture_id", sorted(EXPECTED))
def test_fixture_contract(fixture_id):
    graph = FIXTURES[fixture_id]()
    violations = validate_invariants(graph, CATALOG)
    reports = evaluate_all(graph, violations)
    expected = EXPECTED[fixture_id]
    codes = {violation["code"] for violation in violations}
    assert expected["codes"] <= codes
    assert reports[0]["status"] == expected["status"]
    if not expected["codes"]:
        assert run(graph, CATALOG, SCHEMA)["valid"] is True

    edges = graph.get("edges", [])
    if expected.get("lineage_count") is not None:
        evidences = [edge for edge in edges if edge.get("type") == "EVIDENCES"]
        assert len(set().union(*(set(edge.get("lineage_set", [])) for edge in evidences))) == expected["lineage_count"]
    if expected.get("has_competes"):
        assert any(edge.get("type") == "COMPETES_WITH" for edge in edges)
    if expected.get("has_contradicts") is False:
        assert not any(edge.get("type") == "CONTRADICTS" for edge in edges)
    if expected.get("has_rejection"):
        assert any(edge.get("eligible") is False and edge.get("rejection_reason") for edge in edges)
    if expected.get("excludes_remote_conflict"):
        assert not reports[0]["conflict_edge_ids"]
    if expected.get("excludes_remote_branch"):
        scope_nodes, _ = expected_scope(graph, reports[0]["claim_id"])
        assert "reads-b" not in scope_nodes
        assert "hsp-b" not in scope_nodes
    if expected.get("has_conflict_and_exception"):
        assert reports[0]["conflict_edge_ids"] and reports[0]["exception_edge_ids"]


def test_orphan_evaluation_is_invalid():
    digest = "sha256:" + ("a" * 64)
    graph = {
        "schema_version": "0.2",
        "graph_id": "G-ghost",
        "mapper_version": "0.2.2",
        "rule_catalog_version": "rule-catalog:0.1",
        "rule_catalog_digest": digest,
        "source_manifest_digest": digest,
        "source_artifacts": {"fixture": digest},
        "source_run_id": "ghost-run",
        "created_at": "2026-08-06T12:00:00Z",
        "nodes": [],
        "edges": [],
        "evaluation": [{
            "claim_id": "ghost",
            "status": "NOT_EVALUABLE",
            "used_edge_ids": [],
            "exclusions": [],
            "scope_node_ids": ["ghost"],
            "scope_edge_ids": [],
        }],
    }
    report = run(graph, CATALOG, SCHEMA)
    assert report["valid"] is False
    assert "ORPHAN_EVALUATION" in {
        violation["code"] for violation in report["invariant_violations"]
    }


def test_incomplete_evidence_path_is_invalid():
    graph = FIXTURES["F1"]()
    graph["nodes"] = [node for node in graph["nodes"] if node["type"] in {"EvidenceAggregate", "Claim", "Locus", "Reference"}]
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] == "EVIDENCES"]
    claim_id = next(node["id"] for node in graph["nodes"] if node["type"] == "Claim")
    graph["evaluation"] = [{
        "claim_id": claim_id,
        "status": "NOT_EVALUABLE",
        "used_edge_ids": [graph["edges"][0]["id"]],
        "exclusions": [],
        "scope_node_ids": sorted({claim_id, graph["edges"][0]["source"]}),
        "scope_edge_ids": [graph["edges"][0]["id"]],
    }]
    report = run(graph, CATALOG, SCHEMA)
    assert report["valid"] is False
    assert "INCOMPLETE_EVIDENCE_PATH" in {
        violation["code"] for violation in report["invariant_violations"]
    }


def test_declared_states_must_match_calculation():
    graph = FIXTURES["F1"]()
    claim = next(node for node in graph["nodes"] if node["type"] == "Claim")
    claim["status"] = "CONFLICTED"
    graph["evaluation"][0]["status"] = "NOT_EVALUABLE"
    report = run(graph, CATALOG, SCHEMA)
    assert report["valid"] is False
    assert {violation["code"] for violation in report["invariant_violations"]} >= {
        "CLAIM_STATUS_MISMATCH", "EVALUATION_STATUS_MISMATCH"
    }


def test_catalog_version_must_match_graph():
    graph = FIXTURES["F1"]()
    catalog = deepcopy(CATALOG)
    catalog["rule_catalog_version"] = "rule-catalog:9.9"
    report = run(graph, catalog, SCHEMA)
    assert report["valid"] is False
    assert "CATALOG_VERSION_MISMATCH" in {
        violation["code"] for violation in report["invariant_violations"]
    }


def test_used_edges_must_exist_inside_scope():
    graph = FIXTURES["F1"]()
    graph["evaluation"][0]["used_edge_ids"] = ["ghost-edge"]
    report = run(graph, CATALOG, SCHEMA)
    assert report["valid"] is False
    assert {violation["code"] for violation in report["invariant_violations"]} >= {
        "MISSING_EVALUATION_REFERENCE", "USED_EDGE_OUTSIDE_SCOPE"
    }


def test_null_without_abstention_is_invalid():
    graph = FIXTURES["F1"]()
    hsp = next(node for node in graph["nodes"] if node["type"] == "HSP")
    hsp["matches"] = None
    hsp["observation"] = {
        "observed": True,
        "eligible": True,
        "raw": {},
        "rule_id": "ADMIT-HSP",
    }
    violations = validate_invariants(graph, CATALOG)
    assert "NULL_WITHOUT_ABSTENTION" in {v["code"] for v in violations}


def test_unknown_observation_rule_is_invalid():
    graph = FIXTURES["F1"]()
    hsp = next(node for node in graph["nodes"] if node["type"] == "HSP")
    hsp["observation"]["rule_id"] = "UNKNOWN-RULE-XYZ"
    violations = validate_invariants(graph, CATALOG)
    assert "INACTIVE_OR_UNKNOWN_RULE" in {v["code"] for v in violations}


def test_ineligible_hsp_excluded_from_aggregate():
    graph = FIXTURES["F1"]()
    agg = next(node for node in graph["nodes"] if node["type"] == "EvidenceAggregate")
    hsp_id = agg["derivation"]["input_ids"][0]
    hsp = next(node for node in graph["nodes"] if node["id"] == hsp_id)
    hsp["observation"] = {
        "observed": True,
        "eligible": False,
        "raw": {},
        "rule_id": "ADMIT-HSP",
        "status": "NOT_EVALUABLE",
        "rejection_reason": "DUPLICATE_SOURCE_OBSERVATION",
        "missing_fields": [],
    }
    violations = validate_invariants(graph, CATALOG)
    codes = {v["code"] for v in violations}
    assert "INELIGIBLE_IN_AGGREGATE" in codes or "DUPLICATE_IN_AGGREGATE" in codes


def test_source_digest_mismatch_detected():
    graph = FIXTURES["F1"]()
    graph["source_artifacts"] = {"fixture": "sha256:" + ("a" * 64)}
    for node in graph["nodes"]:
        node["provenance"]["source_digest"] = "sha256:" + ("b" * 64)
    for edge in graph["edges"]:
        edge["provenance"]["source_digest"] = "sha256:" + ("b" * 64)
    violations = validate_invariants(graph, CATALOG)
    assert "SOURCE_DIGEST_MISMATCH" in {v["code"] for v in violations}
