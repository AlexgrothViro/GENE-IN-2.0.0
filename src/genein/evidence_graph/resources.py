"""Default resources relative to the package, independent of working directory."""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CATALOG = PACKAGE_ROOT / "config" / "rule_catalog_0_1.json"
DEFAULT_SCHEMA = PACKAGE_ROOT / "schema" / "evidence_graph_0_2.json"
