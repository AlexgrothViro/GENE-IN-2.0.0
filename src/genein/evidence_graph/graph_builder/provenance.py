"""Proveniência compartilhada entre nós e arestas do Mapper."""
from __future__ import annotations

from typing import Any

from genein.evidence_graph.graph_builder.parse import MAPPER_VERSION, digest_ref, parameters_digest, utc_now_iso


def builder_provenance(
    *,
    source_ref: str,
    digests: dict[str, dict[str, Any]],
    method: str,
    parameters: Any | None = None,
) -> dict[str, str]:
    return {
        "source_system": "evidence-v2",
        "source_ref": source_ref,
        "source_digest": digest_ref(digests, source_ref),
        "method": method,
        "parameters_digest": parameters_digest(parameters if parameters is not None else {}),
        "software": "gene-in-graph-builder",
        "software_version": MAPPER_VERSION,
        "operator_or_agent": "mapper-v0.2.2",
        "recorded_at": utc_now_iso(),
    }
