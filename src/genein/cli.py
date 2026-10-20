"""Application command registration and exit-code propagation."""
from __future__ import annotations

import argparse
from importlib.metadata import version

from genein.evidence_graph.cli import register_commands as register_graph_commands
from genein.pipeline.cli import register_commands as register_pipeline_commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m genein",
        description="Gene-In analysis tools.",
    )
    parser.add_argument("--version", action="version", version=version("genein"))
    commands = parser.add_subparsers(dest="command", required=True)
    register_graph_commands(commands)
    register_pipeline_commands(commands)
    args = parser.parse_args(argv)
    return args.handler(args)
