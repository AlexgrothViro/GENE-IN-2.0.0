"""Application entry point checks using synthetic graph fixtures only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from genein.cli import main
from genein.evidence_graph.graph_builder import cli as builder_cli
from genein.evidence_graph.resources import DEFAULT_CATALOG
from tests.evidence_graph.fixture_graphs import CATALOG, FIXTURES
from tests.evidence_graph.mapper_fixtures import materialize_run


def invoke(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-B", "-m", "genein", *map(str, args)],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=30,
    )


def test_module_entrypoint_without_pythonpath(tmp_path):
    """Editable install (pip install -e .) must expose python -m genein without PYTHONPATH."""
    result = invoke(tmp_path, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage: python -m genein" in result.stdout


@pytest.mark.parametrize("command", [[], ["graph"], ["graph", "build"], ["graph", "validate"]])
def test_help_from_other_directory(tmp_path, command):
    result = invoke(tmp_path, *command, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage: python -m genein" in result.stdout


@pytest.mark.parametrize("command", [[], ["run"], ["graph"], ["graph", "unknown"]])
def test_unavailable_or_incomplete_command_returns_usage_error(tmp_path, command):
    result = invoke(tmp_path, *command)
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_build_and_validate_with_package_defaults_from_other_directory(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    output_root = tmp_path / "output"
    args = ["graph", "build", "--run-dir", run_dir, "--output-root", output_root]
    result = invoke(tmp_path, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["graph_id"] == "G-fixture-alpha2-run"
    graph_dir = Path(summary["graph_dir"])
    assert graph_dir == output_root / summary["graph_id"]
    marker = (graph_dir / "SUCCESS.json").read_bytes()
    result = invoke(tmp_path, "graph", "validate", graph_dir / "evidence_graph.json", DEFAULT_CATALOG)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["valid"] is True
    conflict = invoke(tmp_path, *args)
    assert conflict.returncode == 2
    assert json.loads(conflict.stdout)["ok"] is False
    assert (graph_dir / "SUCCESS.json").read_bytes() == marker


def test_missing_build_catalog_preserves_error_channel_and_code(tmp_path):
    result = invoke(
        tmp_path, "graph", "build", "--run-dir", tmp_path / "missing-run",
        "--output-root", tmp_path / "output", "--rule-catalog", tmp_path / "missing.json",
    )
    assert result.returncode == 2
    assert not result.stdout
    assert json.loads(result.stderr)["ok"] is False


def test_rejected_build_propagates_code_one(monkeypatch, tmp_path, capsys):
    def reject(_request):
        raise ValueError("grafo inválido; artefatos mantidos somente em staging")

    monkeypatch.setattr(builder_cli, "build", reject)
    code = main(["graph", "build", "--run-dir", str(tmp_path), "--output-root", str(tmp_path / "out")])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_invalid_graph_propagates_validation_code_one(tmp_path):
    graph = FIXTURES["F4"]()
    graph_path, catalog_path = tmp_path / "graph.json", tmp_path / "catalog.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    catalog_path.write_text(json.dumps(CATALOG), encoding="utf-8")
    result = invoke(tmp_path, "graph", "validate", graph_path, catalog_path)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["valid"] is False
    assert "MISSING_ENDPOINT" in {entry["code"] for entry in report["invariant_violations"]}


def test_missing_graph_propagates_fatal_code_two(tmp_path):
    result = invoke(tmp_path, "graph", "validate", tmp_path / "missing.json", DEFAULT_CATALOG)
    assert result.returncode == 2
    assert json.loads(result.stdout)["valid"] is False
    assert "fatal_error" in json.loads(result.stdout)
