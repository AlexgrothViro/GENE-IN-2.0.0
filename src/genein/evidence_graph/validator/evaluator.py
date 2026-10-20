from __future__ import annotations

from genein.evidence_graph.validator.invariants import canonical_evidence_paths, expected_scope

PRECEDENCE = ("NOT_EVALUABLE", "CONFLICTED", "INSUFFICIENT", "COHERENT")


def _index(items):
    return {item["id"]: item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)}


def evaluate_claim(graph, claim_id, violations):
    """Calculate structural state inside the declared Claim scope."""
    nodes, edges = _index(graph.get("nodes", [])), _index(graph.get("edges", []))
    evaluations = graph.get("evaluation", [])
    if not isinstance(evaluations, list):
        evaluations = []
    declared = next(
        (evaluation for evaluation in evaluations
         if isinstance(evaluation, dict) and evaluation.get("claim_id") == claim_id),
        None,
    )
    if declared is None:
        return _report(claim_id, "NOT_EVALUABLE", [], [], [], [], [], ["missing_evaluation"])

    scope_nodes = set(declared.get("scope_node_ids", []))
    scope_edges = set(declared.get("scope_edge_ids", []))
    expected_nodes, expected_edges = expected_scope(graph, claim_id)
    local_edges = [edges[edge_id] for edge_id in sorted(scope_edges) if edge_id in edges]
    local_violations = [
        violation
        for violation in violations
        if _touches(violation, scope_nodes, scope_edges, claim_id)
    ]

    paths = canonical_evidence_paths(graph, claim_id)
    evidence = [
        edge["id"] for edge in local_edges
        if edge.get("type") == "EVIDENCES" and edge.get("decision_relevant") is True
    ]
    conflicts = [
        edge["id"] for edge in local_edges
        if edge.get("type") in {"CONTRADICTS", "COMPETES_WITH"}
        and edge.get("decision_relevant") is True
    ]
    exceptions = [edge["id"] for edge in local_edges if edge.get("type") == "EXPLAINS"]
    absences = [
        edge["id"] for edge in local_edges
        if edge.get("observed") is False or edge.get("eligible") is False
    ]

    if local_violations or scope_nodes != expected_nodes or scope_edges != expected_edges or claim_id not in nodes:
        state = "NOT_EVALUABLE"
    elif conflicts:
        state = "CONFLICTED"
    elif not evidence or not paths:
        state = "INSUFFICIENT"
    else:
        state = "COHERENT"
    return _report(
        claim_id,
        state,
        paths,
        evidence,
        absences,
        conflicts,
        exceptions,
        violation_codes=[violation["code"] for violation in local_violations],
    )


def _touches(violation, node_ids, edge_ids, claim_id):
    values = violation.get("evidence", {}).values()
    flattened = {
        item
        for value in values
        for item in (value if isinstance(value, list) else [value])
        if isinstance(item, str)
    }
    return bool(flattened & (node_ids | edge_ids | {claim_id})) or not flattened


def _report(
    claim_id,
    state,
    paths,
    evidence,
    absences,
    conflicts,
    exceptions,
    reasons=None,
    violation_codes=None,
):
    return {
        "claim_id": claim_id,
        "status": state,
        "paths": paths,
        "evidence_edge_ids": sorted(evidence),
        "absence_or_rejection_edge_ids": sorted(absences),
        "conflict_edge_ids": sorted(conflicts),
        "exception_edge_ids": sorted(exceptions),
        "reasons": sorted(reasons or []),
        "violation_codes": sorted(set(violation_codes or [])),
    }


def evaluate_all(graph, violations):
    claim_ids = sorted(
        node["id"]
        for node in graph.get("nodes", [])
        if node.get("type") == "Claim" and isinstance(node.get("id"), str)
    )
    return [evaluate_claim(graph, claim_id, violations) for claim_id in claim_ids]
