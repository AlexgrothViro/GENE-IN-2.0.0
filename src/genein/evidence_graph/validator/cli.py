from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from genein.evidence_graph.validator.evaluator import evaluate_all
from genein.evidence_graph.validator.invariants import check_declared_states, validate_invariants
from genein.evidence_graph.resources import DEFAULT_SCHEMA


def _load(path):
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: raiz JSON deve ser objeto")
    return value


def run(graph, catalog, schema):
    schema_errors = [
        {"path": "/".join(map(str, error.absolute_path)), "message": error.message}
        for error in sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(graph), key=lambda e: list(e.absolute_path))
    ]
    violations = validate_invariants(graph, catalog)
    reports = evaluate_all(graph, violations)
    violations = sorted(
        [*violations, *check_declared_states(graph, reports)],
        key=lambda item: (item["code"], repr(item["evidence"])),
    )
    return {"graph_id": graph.get("graph_id"), "schema_version": graph.get("schema_version"),
            "rule_catalog_version": graph.get("rule_catalog_version"),
            "valid": not schema_errors and not violations,
            "schema_errors": schema_errors, "invariant_violations": violations,
            "claims": reports}


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("graph", type=Path)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)


def execute(args: argparse.Namespace) -> int:
    try:
        report = run(_load(args.graph), _load(args.catalog), _load(args.schema))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        json.dump({"valid": False, "fatal_error": str(exc)}, sys.stdout, ensure_ascii=False, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if report["valid"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validador offline do Grafo de Evidências GENE_IN v0.2")
    configure_parser(parser)
    return execute(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
