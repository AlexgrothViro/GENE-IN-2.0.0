from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

Violation = dict[str, Any]
REJECTION_REASONS = {
    "INCOMPLETE_PROVENANCE", "MISSING_FIELD", "INVALID_COORDINATES",
    "UNKNOWN_RULE", "DEPRECATED_RULE", "DUPLICATE_LINEAGE",
    "DUPLICATE_SOURCE_OBSERVATION", "OUT_OF_DECLARED_SCOPE",
}

# Campos factuais tipados cujo null exige abstenção estrutural.
NULLABLE_FACTUAL_FIELDS = {
    "Contig": ("length", "assembly_method", "sequence_digest"),
    "HSP": (
        "query_length", "alignment_length", "identity_pct", "matches",
        "mismatches", "gaps", "evalue", "bitscore", "strand", "coord_system",
    ),
    "Locus": ("reference_id", "interval", "coord_system"),
    "ReadSupport": ("lineage_id", "read_count", "mapped_bases"),
}
DERIVED_TYPES = {"EVIDENCES", "CONTRADICTS", "COMPETES_WITH", "CONCORDANT_WITH", "EXPLAINS"}
EVALUATIVE_TYPES = DERIVED_TYPES
FACTUAL_TYPES = {
    "DERIVED_FROM", "PROCESSED_FROM", "SUPPORTS", "ASSEMBLED_FROM", "ALIGNS_TO",
    "MATCHES", "LOCATED_IN", "AGGREGATES_INTO",
}

# The edge vocabulary mixes directions. A generic undirected walk crosses into
# sibling branches through shared Run nodes, so ancestry must be explicit.
ANCESTRY_TRANSITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "EvidenceAggregate": (("AGGREGATES_INTO", "incoming"),),
    "HSP": (("ALIGNS_TO", "outgoing"), ("MATCHES", "outgoing"), ("LOCATED_IN", "outgoing")),
    "Contig": (("ASSEMBLED_FROM", "outgoing"), ("SUPPORTS", "incoming")),
    "ReadSupport": (("PROCESSED_FROM", "outgoing"),),
    "Run": (("DERIVED_FROM", "outgoing"),),
}

# Reference and Locus are required side references. The canonical provenance
# spine itself ends at Sample.
CANONICAL_TRANSITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "EvidenceAggregate": (("AGGREGATES_INTO", "incoming"),),
    "HSP": (("ALIGNS_TO", "outgoing"),),
    "Contig": (("ASSEMBLED_FROM", "outgoing"), ("SUPPORTS", "incoming")),
    "ReadSupport": (("PROCESSED_FROM", "outgoing"),),
    "Run": (("DERIVED_FROM", "outgoing"),),
}

ENDPOINTS: dict[str, set[tuple[str, str]]] = {
    "DERIVED_FROM": {("Run", "Sample")},
    "PROCESSED_FROM": {("ReadSupport", "Run")},
    "SUPPORTS": {("ReadSupport", "Contig")},
    "ASSEMBLED_FROM": {("Contig", "ReadSupport")},
    "ALIGNS_TO": {("HSP", "Contig")},
    "MATCHES": {("HSP", "Reference")},
    "LOCATED_IN": {("HSP", "Locus")},
    "AGGREGATES_INTO": {("HSP", "EvidenceAggregate")},
    "EVIDENCES": {("EvidenceAggregate", "Claim")},
    "CONTRADICTS": {("HSP", "Claim"), ("Claim", "Claim")},
    "COMPETES_WITH": {("HSP", "HSP"), ("Claim", "Claim")},
    "CONCORDANT_WITH": {("HSP", "HSP"), ("Claim", "Claim")},
    "EXPLAINS": {("Claim", "Claim")},
}


def _v(code: str, message: str, **evidence: Any) -> Violation:
    return {"code": code, "message": message, "evidence": evidence}


def _nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def _edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]


def _evaluations(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """D11: evaluation is always a list — one document, many Claims."""
    value = graph.get("evaluation", [])
    return [evaluation for evaluation in value if isinstance(evaluation, dict)] if isinstance(value, list) else []


def _directed_neighbors(
    graph: dict[str, Any],
    node_id: str,
    transitions: dict[str, tuple[tuple[str, str], ...]],
) -> list[tuple[str, str]]:
    nodes = _nodes(graph)
    allowed = transitions.get(nodes.get(node_id, {}).get("type"), ())
    neighbors: list[tuple[str, str]] = []
    for edge in _edges(graph):
        for expected_type, direction in allowed:
            if edge.get("type") != expected_type:
                continue
            if direction == "outgoing" and edge.get("source") == node_id:
                neighbors.append((edge.get("target"), edge.get("id")))
            elif direction == "incoming" and edge.get("target") == node_id:
                neighbors.append((edge.get("source"), edge.get("id")))
    return sorted(
        (next_id, edge_id)
        for next_id, edge_id in neighbors
        if isinstance(next_id, str) and isinstance(edge_id, str)
    )


def factual_ancestry(graph: dict[str, Any], start_ids) -> tuple[set[str], set[str]]:
    """Return directed factual ancestry reachable from the supplied nodes."""
    seen = {node_id for node_id in start_ids if isinstance(node_id, str)}
    edge_ids: set[str] = set()
    queue = deque(sorted(seen))
    while queue:
        node_id = queue.popleft()
        for next_id, edge_id in _directed_neighbors(graph, node_id, ANCESTRY_TRANSITIONS):
            edge_ids.add(edge_id)
            if next_id not in seen:
                seen.add(next_id)
                queue.append(next_id)
    return seen, edge_ids


def canonical_evidence_paths(graph: dict[str, Any], claim_id: str) -> list[list[str]]:
    """Return complete typed Sample-to-Claim provenance paths for one Claim."""
    nodes = _nodes(graph)
    paths: list[list[str]] = []
    evidence_edges = [
        edge
        for edge in _edges(graph)
        if edge.get("type") == "EVIDENCES"
        and edge.get("target") == claim_id
        and edge.get("decision_relevant") is True
    ]
    for evidence in sorted(evidence_edges, key=lambda edge: edge.get("id", "")):
        stack = [(evidence.get("source"), [evidence.get("id")], {claim_id})]
        while stack:
            node_id, path, seen = stack.pop()
            if nodes.get(node_id, {}).get("type") == "Sample":
                paths.append(list(reversed(path)))
                continue
            for next_id, edge_id in reversed(_directed_neighbors(graph, node_id, CANONICAL_TRANSITIONS)):
                if next_id not in seen:
                    stack.append((next_id, [*path, edge_id], seen | {node_id}))
    return sorted(paths)


def check_unique_ids(graph, _catalog):
    seen, out = {}, []
    for kind, items in (("node", graph.get("nodes", [])), ("edge", graph.get("edges", []))):
        for item in items if isinstance(items, list) else []:
            item_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(item_id, str):
                out.append(_v("INVALID_ID", f"{kind} sem id string", kind=kind))
            elif item_id in seen:
                out.append(_v("DUPLICATE_ID", "id não é único no documento", id=item_id,
                              first_kind=seen[item_id], duplicate_kind=kind))
            else:
                seen[item_id] = kind
    return out


def check_endpoints_exist(graph, _catalog):
    node_ids = set(_nodes(graph))
    return [
        _v("MISSING_ENDPOINT", "endpoint não existe", edge_id=edge.get("id"), endpoint=key,
           node_id=edge.get(key))
        for edge in _edges(graph)
        for key in ("source", "target")
        if edge.get(key) not in node_ids
    ]


def check_endpoint_types(graph, _catalog):
    nodes = _nodes(graph)
    out = []
    for edge in _edges(graph):
        pair = (nodes.get(edge.get("source"), {}).get("type"), nodes.get(edge.get("target"), {}).get("type"))
        allowed = ENDPOINTS.get(edge.get("type"))
        if allowed is None or pair not in allowed:
            out.append(_v("INVALID_ENDPOINT_TYPES", "tipos de endpoint incompatíveis",
                          edge_id=edge.get("id"), edge_type=edge.get("type"),
                          actual=pair, allowed=sorted(allowed or [])))
    return out


def check_decision_relevant_implies_observed_eligible(graph, _catalog):
    return [
        _v("INVALID_DECISION_RELEVANCE", "decision_relevant exige observed e eligible", edge_id=edge.get("id"))
        for edge in _edges(graph)
        if edge.get("decision_relevant") is True
        and not (edge.get("observed") is True and edge.get("eligible") is True)
    ]


def check_absence_never_contradicts(graph, _catalog):
    out = []
    for edge in _edges(graph):
        if edge.get("type") == "CONTRADICTS":
            derivation = edge.get("derivation", {})
            basis = derivation.get("basis", [])
            markers = {str(value).upper() for value in basis} if isinstance(basis, list) else set()
            if edge.get("observed") is not True or markers & {"ABSENCE", "MISSING", "NOT_OBSERVED"}:
                out.append(_v("ABSENCE_CONTRADICTION", "ausência não pode criar CONTRADICTS",
                              edge_id=edge.get("id")))
    return out


def check_derived_edges_not_independent_observations(graph, _catalog):
    out = []
    for edge in _edges(graph):
        if edge.get("type") in DERIVED_TYPES:
            inputs = edge.get("derivation", {}).get("input_ids", [])
            if not inputs or edge.get("independent_observation") is True:
                out.append(_v("DERIVED_AS_INDEPENDENT", "aresta derivada exige inputs e não é observação independente",
                              edge_id=edge.get("id"), input_ids=inputs))
    return out


def derive_lineage_set(graph, start_ids):
    """Derive lineages through directed factual ancestry; never infer lineage_id."""
    nodes = _nodes(graph)
    ancestry_nodes, _ = factual_ancestry(graph, start_ids)
    return {
        nodes[node_id]["lineage_id"]
        for node_id in ancestry_nodes
        if nodes.get(node_id, {}).get("type") == "ReadSupport"
        and isinstance(nodes[node_id].get("lineage_id"), str)
    }


def check_support_counted_by_lineage(graph, _catalog):
    out = []
    for edge in _edges(graph):
        if edge.get("type") in {"EVIDENCES", "CONCORDANT_WITH"}:
            declared = edge.get("lineage_set")
            derived = derive_lineage_set(graph, [edge.get("source")])
            if not isinstance(declared, list) or set(declared) != derived:
                out.append(_v("LINEAGE_SET_MISMATCH", "suporte deve ser expresso pelo conjunto de lineage_id",
                              edge_id=edge.get("id"), declared=declared, derived=sorted(derived)))
    return out


def check_concordant_lineages_disjoint(graph, _catalog):
    out = []
    for edge in _edges(graph):
        if edge.get("type") == "CONCORDANT_WITH":
            left = derive_lineage_set(graph, [edge.get("source")])
            right = derive_lineage_set(graph, [edge.get("target")])
            overlap = sorted(left & right)
            if overlap:
                out.append(_v("NON_DISJOINT_CONCORDANCE", "CONCORDANT_WITH exige lineage_set disjuntos",
                              edge_id=edge.get("id"), lineage_ids=overlap))
    return out


def _catalog_rules(catalog):
    rules = catalog.get("rules", []) if isinstance(catalog, dict) else []
    if isinstance(rules, dict):
        return rules
    return {
        rule.get("rule_id"): rule
        for rule in rules
        if isinstance(rule, dict) and isinstance(rule.get("rule_id"), str)
    }


def check_rejection_metadata(graph, catalog):
    rules = _catalog_rules(catalog)
    out = []
    for edge in _edges(graph):
        if edge.get("eligible") is False:
            reason, rule_id = edge.get("rejection_reason"), edge.get("rule_id")
            if reason not in REJECTION_REASONS or rule_id not in rules:
                out.append(_v("INVALID_REJECTION_METADATA", "eligible=false exige motivo controlado e rule_id existente",
                              edge_id=edge.get("id"), rejection_reason=reason, rule_id=rule_id))
    return out


def check_evidences_source_aggregate(graph, _catalog):
    nodes = _nodes(graph)
    return [
        _v("DIRECT_HSP_EVIDENCE", "EVIDENCES só pode partir de EvidenceAggregate",
           edge_id=edge.get("id"), source=edge.get("source"))
        for edge in _edges(graph)
        if edge.get("type") == "EVIDENCES"
        and nodes.get(edge.get("source"), {}).get("type") != "EvidenceAggregate"
    ]


def check_derivation_references(graph, _catalog):
    known_ids = set(_nodes(graph)) | {
        edge.get("id") for edge in _edges(graph) if isinstance(edge.get("id"), str)
    }
    out = []
    for owner_kind, items in (("node", graph.get("nodes", [])), ("edge", graph.get("edges", []))):
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("derivation"), dict):
                continue
            missing = sorted(set(item["derivation"].get("input_ids", [])) - known_ids)
            if missing:
                out.append(_v("MISSING_DERIVATION_INPUT", "derivation.input_ids deve referenciar IDs existentes",
                              owner_kind=owner_kind, owner_id=item.get("id"), missing_ids=missing))
    return out


def check_aggregate_references(graph, _catalog):
    nodes = _nodes(graph)
    reference_ids = {
        value
        for node in nodes.values()
        if node.get("type") == "Reference"
        for value in (node.get("id"), node.get("reference_ref"))
        if isinstance(value, str)
    }
    aggregate_edges = {
        (edge.get("source"), edge.get("target"))
        for edge in _edges(graph)
        if edge.get("type") == "AGGREGATES_INTO"
    }
    out = []
    for node in nodes.values():
        if node.get("type") != "EvidenceAggregate":
            continue
        locus_id = node.get("locus_id")
        if nodes.get(locus_id, {}).get("type") != "Locus":
            out.append(_v("INVALID_AGGREGATE_LOCUS", "EvidenceAggregate.locus_id deve apontar para Locus",
                          node_id=node.get("id"), locus_id=locus_id))
        declared_refs = set(node.get("hypothesis", {}).get("reference_ids", []))
        missing_refs = sorted(declared_refs - reference_ids)
        if missing_refs:
            out.append(_v("INVALID_AGGREGATE_REFERENCE", "hypothesis.reference_ids deve apontar para Reference",
                          node_id=node.get("id"), missing_reference_ids=missing_refs))
        for input_id in node.get("derivation", {}).get("input_ids", []):
            if nodes.get(input_id, {}).get("type") != "HSP" or (input_id, node.get("id")) not in aggregate_edges:
                out.append(_v("INVALID_AGGREGATE_INPUT", "inputs do agregado devem ser HSPs ligados por AGGREGATES_INTO",
                              node_id=node.get("id"), input_id=input_id))
    return out


def check_complete_evidence_paths(graph, _catalog):
    out = []
    claim_ids = {
        edge.get("target")
        for edge in _edges(graph)
        if edge.get("type") == "EVIDENCES" and edge.get("decision_relevant") is True
    }
    for claim_id in sorted(value for value in claim_ids if isinstance(value, str)):
        covered = {
            edge_id
            for path in canonical_evidence_paths(graph, claim_id)
            for edge_id in path
        }
        for edge in _edges(graph):
            if (edge.get("type") == "EVIDENCES" and edge.get("target") == claim_id
                    and edge.get("decision_relevant") is True and edge.get("id") not in covered):
                out.append(_v("INCOMPLETE_EVIDENCE_PATH", "EVIDENCES relevante exige caminho factual completo até Sample",
                              claim_id=claim_id, edge_id=edge.get("id")))
    return out


def expected_scope(graph, claim_id):
    """One evaluative hop at Claim plus directed factual ancestry."""
    nodes = {claim_id}
    edge_ids = set()
    frontier = set()
    for edge in _edges(graph):
        if edge.get("type") in EVALUATIVE_TYPES and claim_id in {edge.get("source"), edge.get("target")}:
            edge_ids.add(edge["id"])
            other = edge.get("target") if edge.get("source") == claim_id else edge.get("source")
            nodes.add(other)
            frontier.add(other)
    ancestry_nodes, ancestry_edges = factual_ancestry(graph, frontier)
    nodes.update(ancestry_nodes)
    edge_ids.update(ancestry_edges)
    return nodes, edge_ids


def check_evaluation_integrity(graph, _catalog):
    nodes = _nodes(graph)
    edges = {edge.get("id"): edge for edge in _edges(graph) if isinstance(edge.get("id"), str)}
    claim_ids = {node_id for node_id, node in nodes.items() if node.get("type") == "Claim"}
    evaluations = _evaluations(graph)
    counts = defaultdict(int)
    out = []
    for evaluation in evaluations:
        claim_id = evaluation.get("claim_id")
        counts[claim_id] += 1
        if claim_id not in claim_ids:
            out.append(_v("ORPHAN_EVALUATION", "evaluation.claim_id deve apontar para Claim existente",
                          claim_id=claim_id))
        scope_nodes = set(evaluation.get("scope_node_ids", []))
        scope_edges = set(evaluation.get("scope_edge_ids", []))
        used_edges = set(evaluation.get("used_edge_ids", []))
        missing_nodes = sorted(scope_nodes - set(nodes))
        missing_edges = sorted((scope_edges | used_edges) - set(edges))
        if missing_nodes or missing_edges:
            out.append(_v("MISSING_EVALUATION_REFERENCE", "IDs de evaluation devem existir no documento",
                          claim_id=claim_id, missing_node_ids=missing_nodes, missing_edge_ids=missing_edges))
        if not used_edges <= scope_edges:
            out.append(_v("USED_EDGE_OUTSIDE_SCOPE", "used_edge_ids deve ser subconjunto de scope_edge_ids",
                          claim_id=claim_id, edge_ids=sorted(used_edges - scope_edges)))
    for claim_id in sorted(claim_ids):
        if counts[claim_id] == 0:
            out.append(_v("MISSING_EVALUATION", "cada Claim exige exatamente uma evaluation", claim_id=claim_id))
        elif counts[claim_id] > 1:
            out.append(_v("DUPLICATE_EVALUATION", "cada Claim admite somente uma evaluation",
                          claim_id=claim_id, count=counts[claim_id]))
    return out


def check_evaluation_scope(graph, _catalog):
    out = []
    for evaluation in _evaluations(graph):
        expected_nodes, expected_edges = expected_scope(graph, evaluation.get("claim_id"))
        actual_nodes = set(evaluation.get("scope_node_ids", []))
        actual_edges = set(evaluation.get("scope_edge_ids", []))
        if actual_nodes != expected_nodes or actual_edges != expected_edges:
            out.append(_v("INVALID_SCOPE", "escopo deve ser ancestralidade factual dirigida + 1 hop avaliativo",
                          claim_id=evaluation.get("claim_id"),
                          missing_nodes=sorted(expected_nodes - actual_nodes),
                          extra_nodes=sorted(actual_nodes - expected_nodes),
                          missing_edges=sorted(expected_edges - actual_edges),
                          extra_edges=sorted(actual_edges - expected_edges)))
    return out


def check_active_rules(graph, catalog):
    rules = _catalog_rules(catalog)
    out = []
    for edge in _edges(graph):
        rule = rules.get(edge.get("rule_id"))
        if rule is None or rule.get("status") != "active":
            out.append(_v("INACTIVE_OR_UNKNOWN_RULE", "rule_id deve existir e estar active",
                          edge_id=edge.get("id"), rule_id=edge.get("rule_id"),
                          status=rule.get("status") if rule else None))
    return out


def check_catalog_version(graph, catalog):
    declared = graph.get("rule_catalog_version")
    actual = catalog.get("rule_catalog_version") if isinstance(catalog, dict) else None
    if declared != actual:
        return [_v("CATALOG_VERSION_MISMATCH", "grafo e catálogo devem declarar a mesma versão",
                   graph_version=declared, catalog_version=actual)]
    return []


def check_readsupport_lineage_present(graph, _catalog):
    out = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "ReadSupport":
            continue
        lineage = node.get("lineage_id")
        if isinstance(lineage, str) and lineage:
            continue
        obs = node.get("observation") if isinstance(node.get("observation"), dict) else {}
        missing = obs.get("missing_fields") if isinstance(obs.get("missing_fields"), list) else []
        if obs.get("eligible") is False and "lineage_id" in missing:
            continue
        out.append(_v(
            "MISSING_LINEAGE_ID",
            "ReadSupport exige lineage_id declarado ou abstenção com missing_fields",
            node_id=node.get("id"),
        ))
    return out


def check_null_only_with_abstention(graph, _catalog):
    """null só em observação inelegível e listado em missing_fields; zero real permanece zero."""
    out = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        fields = NULLABLE_FACTUAL_FIELDS.get(node.get("type"), ())
        if not fields:
            continue
        obs = node.get("observation") if isinstance(node.get("observation"), dict) else {}
        missing = set(obs.get("missing_fields") or [])
        eligible = obs.get("eligible")
        for field in fields:
            if field not in node:
                continue
            value = node.get(field)
            if value is None:
                if eligible is not False or field not in missing:
                    out.append(_v(
                        "NULL_WITHOUT_ABSTENTION",
                        "null factual exige eligible=false e campo em missing_fields",
                        node_id=node.get("id"),
                        field=field,
                    ))
            elif eligible is True:
                continue  # zero real (0 / 0.0) permanece válido
    return out


def check_provenance_source_artifacts(graph, _catalog):
    artifacts = graph.get("source_artifacts")
    if not isinstance(artifacts, dict):
        return []
    out = []
    for kind, items in (("node", graph.get("nodes", [])), ("edge", graph.get("edges", []))):
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            prov = item.get("provenance")
            if not isinstance(prov, dict):
                continue
            source_ref = prov.get("source_ref")
            source_digest = prov.get("source_digest")
            if source_ref not in artifacts:
                out.append(_v(
                    "UNKNOWN_SOURCE_REF",
                    "provenance.source_ref deve existir em source_artifacts",
                    owner_kind=kind,
                    owner_id=item.get("id"),
                    source_ref=source_ref,
                ))
                continue
            expected = artifacts[source_ref]
            if source_digest != expected:
                out.append(_v(
                    "SOURCE_DIGEST_MISMATCH",
                    "provenance.source_digest deve coincidir com source_artifacts",
                    owner_kind=kind,
                    owner_id=item.get("id"),
                    source_ref=source_ref,
                    declared=source_digest,
                    expected=expected,
                ))
    return out


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def check_graph_provenance_envelope(graph, _catalog):
    """Validate mapper provenance fields required on the graph root."""
    out = []
    for field in (
        "mapper_version",
        "rule_catalog_digest",
        "source_manifest_digest",
        "source_artifacts",
        "source_run_id",
        "created_at",
    ):
        if field not in graph:
            out.append(_v(
                "MISSING_GRAPH_PROVENANCE_FIELD",
                f"campo raiz obrigatório ausente: {field}",
                field=field,
            ))

    for field in ("rule_catalog_digest", "source_manifest_digest"):
        value = graph.get(field)
        if value is not None and not (
            isinstance(value, str) and _DIGEST_RE.fullmatch(value)
        ):
            out.append(_v(
                "INVALID_GRAPH_DIGEST",
                f"{field} deve coincidir com sha256:[64 hex]",
                field=field,
                value=value,
            ))

    artifacts = graph.get("source_artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, dict) or not artifacts:
            out.append(_v(
                "INVALID_SOURCE_ARTIFACTS",
                "source_artifacts deve ser um mapa não vazio",
            ))
        elif isinstance(artifacts, dict):
            for ref, digest in artifacts.items():
                if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
                    out.append(_v(
                        "INVALID_SOURCE_ARTIFACT_DIGEST",
                        "source_artifacts[*] deve coincidir com sha256:[64 hex]",
                        source_ref=ref,
                        value=digest,
                    ))

    run_id = graph.get("source_run_id")
    if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
        out.append(_v(
            "INVALID_SOURCE_RUN_ID",
            "source_run_id deve ser string não vazia",
            value=run_id,
        ))

    created_at = graph.get("created_at")
    if created_at is not None:
        if not isinstance(created_at, str) or not created_at.strip():
            out.append(_v(
                "INVALID_CREATED_AT",
                "created_at deve ser string date-time parseável",
                value=created_at,
            ))
        else:
            try:
                datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                out.append(_v(
                    "INVALID_CREATED_AT",
                    "created_at deve ser string date-time parseável",
                    value=created_at,
                ))

    if isinstance(run_id, str) and run_id.strip():
        run_nodes = [
            node for node in graph.get("nodes", [])
            if isinstance(node, dict) and node.get("type") == "Run"
        ]
        if run_nodes and all(node.get("run_ref") != run_id for node in run_nodes):
            out.append(_v(
                "SOURCE_RUN_ID_MISMATCH",
                "source_run_id deve coincidir com Run.run_ref",
                source_run_id=run_id,
                run_refs=[node.get("run_ref") for node in run_nodes],
            ))
    return out


def check_observation_rules(graph, catalog):
    rules = _catalog_rules(catalog)
    out = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        obs = node.get("observation")
        if not isinstance(obs, dict):
            continue
        rule_id = obs.get("rule_id")
        if rule_id not in rules or rules[rule_id].get("status") != "active":
            out.append(_v(
                "INACTIVE_OR_UNKNOWN_RULE",
                "observation.rule_id deve existir e estar active",
                node_id=node.get("id"),
                rule_id=rule_id,
            ))
        if obs.get("eligible") is False:
            reason = obs.get("rejection_reason")
            if reason not in REJECTION_REASONS:
                out.append(_v(
                    "INVALID_REJECTION_METADATA",
                    "eligible=false exige rejection_reason controlado",
                    node_id=node.get("id"),
                    rejection_reason=reason,
                ))
            if obs.get("status") != "NOT_EVALUABLE":
                out.append(_v(
                    "INVALID_OBSERVATION_STATUS",
                    "observação inelegível exige status=NOT_EVALUABLE",
                    node_id=node.get("id"),
                    status=obs.get("status"),
                ))
            if not isinstance(obs.get("missing_fields"), list):
                out.append(_v(
                    "INVALID_OBSERVATION_MISSING_FIELDS",
                    "observação inelegível exige missing_fields",
                    node_id=node.get("id"),
                ))
    return out


def check_ineligible_excluded_from_aggregates(graph, _catalog):
    nodes = _nodes(graph)
    out = []
    for node in nodes.values():
        if node.get("type") != "EvidenceAggregate":
            continue
        for input_id in node.get("derivation", {}).get("input_ids", []):
            hsp = nodes.get(input_id, {})
            obs = hsp.get("observation") if isinstance(hsp.get("observation"), dict) else {}
            if hsp.get("type") != "HSP":
                continue
            if obs.get("eligible") is not True:
                out.append(_v(
                    "INELIGIBLE_IN_AGGREGATE",
                    "derivation.input_ids do agregado só admite HSP elegível",
                    aggregate_id=node.get("id"),
                    input_id=input_id,
                ))
            if obs.get("rejection_reason") == "DUPLICATE_SOURCE_OBSERVATION":
                out.append(_v(
                    "DUPLICATE_IN_AGGREGATE",
                    "HSP duplicado não entra em agregado",
                    aggregate_id=node.get("id"),
                    input_id=input_id,
                ))
    return out


def check_explains_additive(graph, _catalog):
    edges = _edges(graph)
    contradict_claims = {edge.get("target") for edge in edges if edge.get("type") == "CONTRADICTS"}
    return [
        _v("ORPHAN_EXPLANATION", "EXPLAINS exige CONTRADICTS coexistente e nunca o substitui",
           edge_id=edge.get("id"), claim_id=edge.get("target"))
        for edge in edges
        if edge.get("type") == "EXPLAINS" and edge.get("target") not in contradict_claims
    ]


def check_exception_does_not_change_state(graph, _catalog):
    edges = _edges(graph)
    conflicted = {
        edge.get("target")
        for edge in edges
        if edge.get("type") == "CONTRADICTS" and edge.get("decision_relevant") is True
    }
    explained = {edge.get("target") for edge in edges if edge.get("type") == "EXPLAINS"}
    out = []
    for evaluation in _evaluations(graph):
        claim_id = evaluation.get("claim_id")
        if claim_id in conflicted & explained and evaluation.get("status") != "CONFLICTED":
            out.append(_v("EXCEPTION_CHANGED_STATE", "EXPLAINS não altera CONFLICTED",
                          claim_id=claim_id, status=evaluation.get("status")))
    return out


CHECKS = (
    check_unique_ids,
    check_endpoints_exist,
    check_endpoint_types,
    check_decision_relevant_implies_observed_eligible,
    check_absence_never_contradicts,
    check_derived_edges_not_independent_observations,
    check_support_counted_by_lineage,
    check_concordant_lineages_disjoint,
    check_rejection_metadata,
    check_evidences_source_aggregate,
    check_derivation_references,
    check_aggregate_references,
    check_complete_evidence_paths,
    check_evaluation_integrity,
    check_evaluation_scope,
    check_active_rules,
    check_catalog_version,
    check_readsupport_lineage_present,
    check_explains_additive,
    check_exception_does_not_change_state,
    check_null_only_with_abstention,
    check_graph_provenance_envelope,
    check_provenance_source_artifacts,
    check_observation_rules,
    check_ineligible_excluded_from_aggregates,
)


def validate_invariants(graph, catalog):
    violations = []
    for check in CHECKS:
        try:
            violations.extend(check(graph, catalog))
        except (KeyError, TypeError, ValueError) as exc:
            violations.append(_v("CHECK_INPUT_ERROR", "entrada malformada impediu verificação",
                                 check=check.__name__, error=str(exc)))
    return sorted(violations, key=lambda item: (item["code"], repr(item["evidence"])))


def check_declared_states(graph: dict[str, Any], reports: list[dict[str, Any]]) -> list[Violation]:
    """Require both serialized status fields to match the deterministic result."""
    nodes = _nodes(graph)
    evaluations = {evaluation.get("claim_id"): evaluation for evaluation in _evaluations(graph)}
    out = []
    for report in reports:
        claim_id = report.get("claim_id")
        calculated = report.get("status")
        claim_status = nodes.get(claim_id, {}).get("status")
        evaluation_status = evaluations.get(claim_id, {}).get("status")
        if claim_status != calculated:
            out.append(_v("CLAIM_STATUS_MISMATCH", "Claim.status diverge do estado calculado",
                          claim_id=claim_id, declared=claim_status, calculated=calculated))
        if evaluation_status != calculated:
            out.append(_v("EVALUATION_STATUS_MISMATCH", "evaluation.status diverge do estado calculado",
                          claim_id=claim_id, declared=evaluation_status, calculated=calculated))
    return out
