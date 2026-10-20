"""Contrato v0.2.1: as três emendas que separam o pacote anterior da spec vigente.

Cobre D10 (EXPLAINS só Claim→Claim), D11 (evaluation sempre lista) e
D13 (PROCESSED_FROM: ReadSupport→Run). Não depende das fixtures F1–F10.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from genein.evidence_graph.resources import DEFAULT_SCHEMA
from jsonschema import Draft202012Validator

from genein.evidence_graph.validator.invariants import ENDPOINTS, FACTUAL_TYPES, check_endpoint_types

SCHEMA_PATH = DEFAULT_SCHEMA


@pytest.fixture(scope="module")
def schema():
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _edge(edge_id, edge_type, source, target):
    return {"id": edge_id, "type": edge_type, "source": source, "target": target}


def _graph(edges):
    nodes = [
        {"id": "n-sample", "type": "Sample"},
        {"id": "n-run", "type": "Run"},
        {"id": "n-support", "type": "ReadSupport"},
        {"id": "n-hsp", "type": "HSP"},
        {"id": "n-claim-a", "type": "Claim"},
        {"id": "n-claim-b", "type": "Claim"},
    ]
    return {"nodes": nodes, "edges": edges, "evaluation": []}


# D13 — PROCESSED_FROM

def test_processed_from_is_in_schema_edge_enum(schema):
    assert "PROCESSED_FROM" in schema["$defs"]["edge"]["properties"]["type"]["enum"]


def test_processed_from_is_factual():
    assert "PROCESSED_FROM" in FACTUAL_TYPES


def test_processed_from_endpoints_are_readsupport_to_run():
    assert ENDPOINTS["PROCESSED_FROM"] == {("ReadSupport", "Run")}


def test_processed_from_accepts_readsupport_to_run():
    graph = _graph([_edge("e1", "PROCESSED_FROM", "n-support", "n-run")])
    assert check_endpoint_types(graph, {}) == []


def test_processed_from_rejects_reversed_direction():
    graph = _graph([_edge("e1", "PROCESSED_FROM", "n-run", "n-support")])
    violations = check_endpoint_types(graph, {})
    assert [v["code"] for v in violations] == ["INVALID_ENDPOINT_TYPES"]


def test_canonical_path_sample_to_claim_is_satisfiable():
    """O furo normativo da v0.1: Run↔ReadSupport não existia."""
    graph = _graph([
        _edge("e1", "DERIVED_FROM", "n-run", "n-sample"),
        _edge("e2", "PROCESSED_FROM", "n-support", "n-run"),
    ])
    assert check_endpoint_types(graph, {}) == []


# D10 — EXPLAINS só Claim→Claim

def test_explains_endpoints_are_claim_to_claim_only():
    assert ENDPOINTS["EXPLAINS"] == {("Claim", "Claim")}


def test_explains_accepts_claim_to_claim():
    graph = _graph([_edge("e1", "EXPLAINS", "n-claim-a", "n-claim-b")])
    assert check_endpoint_types(graph, {}) == []


def test_explains_rejects_hsp_to_claim():
    graph = _graph([_edge("e1", "EXPLAINS", "n-hsp", "n-claim-a")])
    violations = check_endpoint_types(graph, {})
    assert [v["code"] for v in violations] == ["INVALID_ENDPOINT_TYPES"]


# D11 — evaluation sempre lista

def test_schema_evaluation_is_always_an_array(schema):
    evaluation = schema["properties"]["evaluation"]
    assert "oneOf" not in evaluation
    assert evaluation["type"] == "array"
    assert evaluation["minItems"] == 0
    assert evaluation["items"] == {"$ref": "#/$defs/evaluation"}


def test_schema_is_parseable_and_draft_2020_12(schema):
    """O pacote anterior entregou este arquivo com JSON malformado (allOf de edge).

    `jsonschema` é dependência declarada do pacote, não opcional: se faltar, a suíte
    quebra alto em vez de sumir com este teste e reportar um verde falso.
    """
    Draft202012Validator.check_schema(schema)
