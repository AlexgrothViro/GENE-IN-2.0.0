"""Register evidence graph commands on the application CLI."""
from genein.evidence_graph.graph_builder import cli as builder_cli
from genein.evidence_graph.validator import cli as validator_cli


def register_commands(commands) -> None:
    graph = commands.add_parser("graph", help="Build or validate an evidence graph.")
    actions = graph.add_subparsers(dest="graph_command", required=True)
    build = actions.add_parser("build", help="Project a promoted Evidence V2 run.")
    builder_cli.configure_parser(build)
    build.set_defaults(handler=builder_cli.execute)
    validate = actions.add_parser("validate", help="Validate a graph offline.")
    validator_cli.configure_parser(validate)
    validate.set_defaults(handler=validator_cli.execute)
