from __future__ import annotations

from copy import deepcopy

from genein.evidence_graph.validator.invariants import expected_scope

CATALOG = {
    "rule_catalog_version": "rule-catalog:0.1",
    "rules": [
        {"rule_id": rule_id, "status": "active"}
        for rule_id in (
            "ADMIT-DERIVED_FROM",
            "ADMIT-PROCESSED_FROM",
            "ADMIT-SUPPORTS",
            "ADMIT-ASSEMBLED_FROM",
            "ADMIT-ALIGNS_TO",
            "ADMIT-MATCHES",
            "ADMIT-LOCATED_IN",
            "ADMIT-AGGREGATES_INTO",
            "ADMIT-HSP",
            "ADMIT-CONTIG",
            "ADMIT-LOCUS",
            "ADMIT-READSUPPORT",
            "ADMIT-TEMPLATE-LINEAGE",
            "ADMIT-MAPPER",
            "EVIDENCES-001",
            "CONTRADICTS-001",
            "COMPETES-001",
            "CONCORDANT-001",
            "EXCEPTION-COINFECTION",
        )
    ],
}

PROVENANCE = {
    "source_system": "synthetic-fixture",
    "source_ref": "fixture",
    "source_digest": "sha256:" + ("a" * 64),
    "method": "deterministic-test-builder",
    "parameters_digest": "sha256:" + ("b" * 64),
    "software": "pytest",
    "software_version": "1",
    "operator_or_agent": "gene-in-tests",
    "recorded_at": "2026-08-06T12:00:00Z",
}

FIXTURE_DIGEST = "sha256:" + ("a" * 64)

RULE_BY_EDGE = {
    "DERIVED_FROM": "ADMIT-DERIVED_FROM",
    "PROCESSED_FROM": "ADMIT-PROCESSED_FROM",
    "SUPPORTS": "ADMIT-SUPPORTS",
    "ASSEMBLED_FROM": "ADMIT-ASSEMBLED_FROM",
    "ALIGNS_TO": "ADMIT-ALIGNS_TO",
    "MATCHES": "ADMIT-MATCHES",
    "LOCATED_IN": "ADMIT-LOCATED_IN",
    "AGGREGATES_INTO": "ADMIT-AGGREGATES_INTO",
    "EVIDENCES": "EVIDENCES-001",
    "CONTRADICTS": "CONTRADICTS-001",
    "COMPETES_WITH": "COMPETES-001",
    "CONCORDANT_WITH": "CONCORDANT-001",
    "EXPLAINS": "EXCEPTION-COINFECTION",
}


def _eligible_observation(rule_id: str, raw: dict | None = None) -> dict:
    return {
        "observed": True,
        "eligible": True,
        "raw": raw or {},
        "rule_id": rule_id,
    }


def _node(node_id: str, node_type: str, **values):
    node = {"id": node_id, "type": node_type, "provenance": deepcopy(PROVENANCE)}
    required = {
        "Sample": {"sample_ref": node_id},
        "Run": {"run_ref": node_id, "toolchain": {"name": "fixture"}},
        "ReadSupport": {
            "support_ref": node_id,
            "observation": _eligible_observation("ADMIT-READSUPPORT", {"kind": "paired"}),
            "lineage_id": f"lineage-{node_id}",
            "read_count": 2,
            "mapped_bases": 200,
        },
        "Contig": {
            "contig_ref": node_id,
            "length": 200,
            "assembly_method": "fixture",
            "sequence_digest": f"sha256:{node_id}",
            "observation": _eligible_observation("ADMIT-CONTIG"),
        },
        "HSP": {
            "hsp_ref": node_id,
            "query_length": 100,
            "alignment_length": 100,
            "identity_pct": 99.0,
            "matches": 99,
            "mismatches": 1,
            "gaps": 0,
            "evalue": 1e-20,
            "bitscore": 180.0,
            "strand": "+",
            "coord_system": "1-based-inclusive",
            "observation": _eligible_observation("ADMIT-HSP"),
        },
        "Reference": {"reference_ref": node_id},
        "Locus": {
            "reference_id": values.get("reference_id", node_id.replace("locus", "reference")),
            "interval": [1, 100],
            "coord_system": "1-based-inclusive",
            "observation": _eligible_observation("ADMIT-LOCUS"),
        },
        "Claim": {"claim_kind": "TARGET_PRESENT", "status": values.get("status", "COHERENT")},
    }
    node.update(required.get(node_type, {}))
    node.update(values)
    return node


def _edge(edge_id: str, edge_type: str, source: str, target: str, **values):
    edge = {
        "id": edge_id,
        "type": edge_type,
        "source": source,
        "target": target,
        "observed": True,
        "eligible": True,
        "decision_relevant": values.pop("decision_relevant", True),
        "rule_id": RULE_BY_EDGE[edge_type],
        "provenance": deepcopy(PROVENANCE),
        "created_at": "2026-08-06T12:00:00Z",
    }
    if edge_type in {"EVIDENCES", "CONTRADICTS", "COMPETES_WITH", "CONCORDANT_WITH", "EXPLAINS"}:
        edge["derivation"] = {
            "input_ids": values.pop("input_ids", [source]),
            "evaluator_version": "fixture-1",
        }
    edge.update(values)
    return edge


def _branch(prefix: str = "a", *, run_id: str | None = None, evidence_relevant: bool = True):
    ids = {name: f"{name}-{prefix}" for name in (
        "sample", "run", "reads", "contig", "hsp", "reference", "locus", "aggregate", "claim"
    )}
    if run_id is not None:
        ids["run"] = run_id
    lineage = f"lineage-{prefix}"
    nodes = [
        _node(ids["sample"], "Sample"),
        _node(ids["run"], "Run"),
        _node(ids["reads"], "ReadSupport", lineage_id=lineage),
        _node(ids["contig"], "Contig"),
        _node(ids["hsp"], "HSP"),
        _node(ids["reference"], "Reference"),
        _node(ids["locus"], "Locus", reference_id=ids["reference"]),
        _node(
            ids["aggregate"],
            "EvidenceAggregate",
            locus_id=ids["locus"],
            hypothesis={"reference_ids": [ids["reference"]]},
            aggregation_method="UNION_ALL_ELIGIBLE",
            derivation={"input_ids": [ids["hsp"]], "evaluator_version": "fixture-1"},
        ),
        _node(ids["claim"], "Claim"),
    ]
    edges = [
        _edge(f"derived-{prefix}", "DERIVED_FROM", ids["run"], ids["sample"]),
        _edge(f"processed-{prefix}", "PROCESSED_FROM", ids["reads"], ids["run"]),
        _edge(f"assembled-{prefix}", "ASSEMBLED_FROM", ids["contig"], ids["reads"]),
        _edge(f"aligns-{prefix}", "ALIGNS_TO", ids["hsp"], ids["contig"]),
        _edge(f"matches-{prefix}", "MATCHES", ids["hsp"], ids["reference"]),
        _edge(f"located-{prefix}", "LOCATED_IN", ids["hsp"], ids["locus"]),
        _edge(f"aggregates-{prefix}", "AGGREGATES_INTO", ids["hsp"], ids["aggregate"]),
        _edge(
            f"evidences-{prefix}",
            "EVIDENCES",
            ids["aggregate"],
            ids["claim"],
            input_ids=[ids["aggregate"]],
            lineage_set=[lineage],
            decision_relevant=evidence_relevant,
        ),
    ]
    return ids, nodes, edges


def _graph(nodes, edges):
    run_ref = next(
        (node.get("run_ref") for node in nodes if node.get("type") == "Run"),
        "fixture-run",
    )
    return {
        "schema_version": "0.2",
        "graph_id": "G-fixture",
        "mapper_version": "0.2.2",
        "rule_catalog_version": "rule-catalog:0.1",
        "rule_catalog_digest": FIXTURE_DIGEST,
        "source_manifest_digest": FIXTURE_DIGEST,
        "source_artifacts": {"fixture": FIXTURE_DIGEST},
        "source_run_id": run_ref,
        "created_at": "2026-08-06T12:00:00Z",
        "nodes": nodes,
        "edges": edges,
        "evaluation": [],
    }


def _set_evaluations(graph, status_by_claim):
    for node in graph["nodes"]:
        if node.get("type") == "Claim":
            node["status"] = status_by_claim[node["id"]]
    evaluations = []
    for claim_id, status in sorted(status_by_claim.items()):
        scope_nodes, scope_edges = expected_scope(graph, claim_id)
        used_edges = sorted(
            edge["id"]
            for edge in graph["edges"]
            if edge["id"] in scope_edges and edge.get("decision_relevant") is True
        )
        evaluations.append({
            "claim_id": claim_id,
            "status": status,
            "used_edge_ids": used_edges,
            "exclusions": [],
            "scope_node_ids": sorted(scope_nodes),
            "scope_edge_ids": sorted(scope_edges),
        })
    graph["evaluation"] = evaluations
    return graph


def fixture_f1():
    ids, nodes, edges = _branch("a")
    return _set_evaluations(_graph(nodes, edges), {ids["claim"]: "COHERENT"})


def fixture_f2():
    ids, nodes, edges = _branch("a")
    edges.append(_edge("contradicts-a", "CONTRADICTS", ids["hsp"], ids["claim"], input_ids=[ids["hsp"]]))
    return _set_evaluations(_graph(nodes, edges), {ids["claim"]: "CONFLICTED"})


def fixture_f3():
    ids, nodes, edges = _branch("a", evidence_relevant=False)
    return _set_evaluations(_graph(nodes, edges), {ids["claim"]: "INSUFFICIENT"})


def fixture_f4():
    ids, nodes, edges = _branch("a")
    next(edge for edge in edges if edge["type"] == "ALIGNS_TO")["target"] = "missing-contig"
    return _set_evaluations(_graph(nodes, edges), {ids["claim"]: "NOT_EVALUABLE"})


def fixture_f5():
    ids, nodes, edges = _branch("a")
    second_hsp = "hsp-a2"
    nodes.append(_node(second_hsp, "HSP"))
    edges.extend([
        _edge("aligns-a2", "ALIGNS_TO", second_hsp, ids["contig"]),
        _edge("matches-a2", "MATCHES", second_hsp, ids["reference"]),
        _edge("located-a2", "LOCATED_IN", second_hsp, ids["locus"]),
        _edge("aggregates-a2", "AGGREGATES_INTO", second_hsp, ids["aggregate"]),
    ])
    aggregate = next(node for node in nodes if node["id"] == ids["aggregate"])
    aggregate["derivation"]["input_ids"].append(second_hsp)
    return _set_evaluations(_graph(nodes, edges), {ids["claim"]: "COHERENT"})


def fixture_f6():
    ids, nodes, edges = _branch("a")
    other_claim = _node("claim-b", "Claim", status="CONFLICTED")
    nodes.append(other_claim)
    edges.append(_edge("competes-a-b", "COMPETES_WITH", other_claim["id"], ids["claim"],
                       input_ids=[other_claim["id"], ids["claim"]]))
    return _set_evaluations(
        _graph(nodes, edges),
        {ids["claim"]: "CONFLICTED", other_claim["id"]: "CONFLICTED"},
    )


def fixture_f7():
    ids_a, nodes_a, edges_a = _branch("a")
    ids_b, nodes_b, edges_b = _branch("b", run_id=ids_a["run"])
    nodes_b = [node for node in nodes_b if node["id"] not in {ids_b["run"], ids_b["sample"]}]
    edges_b = [edge for edge in edges_b if edge["type"] != "DERIVED_FROM"]
    next(edge for edge in edges_b if edge["type"] == "ALIGNS_TO")["target"] = "missing-contig-b"
    graph = _graph(nodes_a + nodes_b, edges_a + edges_b)
    return _set_evaluations(
        graph,
        {ids_a["claim"]: "COHERENT", ids_b["claim"]: "NOT_EVALUABLE"},
    )


def fixture_f8():
    ids, nodes, edges = _branch("a")
    edges.append(_edge(
        "rejected-a",
        "MATCHES",
        ids["hsp"],
        ids["reference"],
        eligible=False,
        decision_relevant=False,
        rejection_reason="MISSING_FIELD",
    ))
    return _set_evaluations(_graph(nodes, edges), {ids["claim"]: "COHERENT"})


def fixture_f9():
    ids, nodes, edges = _branch("a")
    claim_b = _node("claim-b", "Claim", status="CONFLICTED")
    claim_c = _node("claim-c", "Claim", status="CONFLICTED")
    nodes.extend([claim_b, claim_c])
    edges.extend([
        _edge("concordant-a-b", "CONCORDANT_WITH", claim_b["id"], ids["claim"],
              input_ids=[claim_b["id"], ids["claim"]], lineage_set=[]),
        _edge("contradicts-b-c", "CONTRADICTS", claim_c["id"], claim_b["id"],
              input_ids=[claim_c["id"], claim_b["id"]]),
    ])
    return _set_evaluations(
        _graph(nodes, edges),
        {ids["claim"]: "COHERENT", claim_b["id"]: "CONFLICTED", claim_c["id"]: "CONFLICTED"},
    )


def fixture_f10():
    ids, nodes, edges = _branch("a")
    exception_claim = _node("claim-exception", "Claim", status="INSUFFICIENT")
    nodes.append(exception_claim)
    edges.extend([
        _edge("contradicts-a", "CONTRADICTS", ids["hsp"], ids["claim"], input_ids=[ids["hsp"]]),
        _edge("explains-a", "EXPLAINS", exception_claim["id"], ids["claim"],
              input_ids=[exception_claim["id"], ids["claim"]], rationale="coinfection fixture"),
    ])
    return _set_evaluations(
        _graph(nodes, edges),
        {ids["claim"]: "CONFLICTED", exception_claim["id"]: "INSUFFICIENT"},
    )


FIXTURES = {
    "F1": fixture_f1,
    "F2": fixture_f2,
    "F3": fixture_f3,
    "F4": fixture_f4,
    "F5": fixture_f5,
    "F6": fixture_f6,
    "F7": fixture_f7,
    "F8": fixture_f8,
    "F9": fixture_f9,
    "F10": fixture_f10,
}
