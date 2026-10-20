"""CLI do graph_builder — Mapper v0.2.2."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from genein.evidence_graph.graph_builder.parse import MAPPER_VERSION
from genein.evidence_graph.graph_builder.pipeline import build
from genein.evidence_graph.graph_builder.types import BuildRequest
from genein.evidence_graph.graph_builder.writer import DestinationExistsError, StagingConflictError

from genein.evidence_graph.resources import DEFAULT_CATALOG


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--rule-catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="Catálogo de regras (default: catálogo incluído no pacote genein).",
    )


def execute(args: argparse.Namespace) -> int:
    if not args.rule_catalog.is_file():
        print(
            json.dumps({
                "ok": False,
                "error": f"catálogo ausente: {args.rule_catalog}",
                "mapper_version": MAPPER_VERSION,
            }),
            file=sys.stderr,
        )
        return 2

    request = BuildRequest(
        run_dir=args.run_dir,
        output_root=args.output_root,
        rule_catalog_path=args.rule_catalog,
    )
    try:
        result = build(request)
    except (DestinationExistsError, StagingConflictError, ValueError) as exc:
        message = str(exc)
        rejected = "inválido" in message or "mantidos somente em staging" in message
        payload = {
            "ok": False,
            "error": message,
            "mapper_version": MAPPER_VERSION,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1 if rejected else 2
    except OSError as exc:
        print(json.dumps({
            "ok": False,
            "error": str(exc),
            "mapper_version": MAPPER_VERSION,
        }, ensure_ascii=False))
        return 2

    print(json.dumps({
        "ok": True,
        "graph_id": result.graph_id,
        "graph_dir": str(result.graph_dir),
        "graph_digest": result.graph_digest,
        "valid": result.valid,
        "mapper_version": MAPPER_VERSION,
    }, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m genein.evidence_graph.graph_builder.cli")
    configure_parser(parser)
    return execute(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
