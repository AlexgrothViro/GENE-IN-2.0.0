"""3. Validator — schema + invariantes estruturais."""
from __future__ import annotations

import json
from typing import Any

from genein.evidence_graph.resources import DEFAULT_SCHEMA


def validate(graph: dict[str, Any], catalog: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Relatório de validator.cli.run."""
    from genein.evidence_graph.validator.cli import run

    if schema is None:
        schema = json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))
    return run(graph, catalog, schema)
