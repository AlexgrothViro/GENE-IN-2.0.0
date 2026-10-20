"""Tipos de fronteira entre os cinco componentes do builder.

Sem lógica: só o formato do que atravessa cada seta do pipeline
Reader → Mapper → Validator → Evaluator → Writer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BuildRequest:
    """Entrada do builder: uma execução Evidence V2 promovida e imutável."""

    run_dir: Path
    """Diretório `results/evidence/runs/<RUN_ID>` — precisa conter SUCCESS.json."""

    output_root: Path
    """Raiz da área derivada própria. Nunca aponta para dentro do pipeline."""

    rule_catalog_path: Path
    """Catálogo de rule_id versionado (`rule-catalog:X.Y`)."""


@dataclass(frozen=True)
class SourceArtifacts:
    """Saída do Reader: artefatos lidos, com o digest que os torna citáveis.

    `digests` é `artifact_manifest.json["files"]` — caminho relativo → {size, sha256}.
    Todo nó e aresta emitidos pelo Mapper referenciam uma entrada daqui em
    `provenance.source_ref` / `provenance.source_digest`.
    """

    run_id: str
    run_dir: Path
    digests: dict[str, dict[str, Any]]
    tables: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    """TSVs promovidos, por nome de arquivo, já em linhas-dicionário."""
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    """JSONs promovidos (sample_evidence, provenance, run_state, SUCCESS)."""


@dataclass(frozen=True)
class MapperOutput:
    """Saída do Mapper: grafo parcial + TSVs derivados factuais."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    aggregates: list[dict[str, Any]]
    hsp_evidence_rows: list[dict[str, Any]]
    template_lineage_rows: list[dict[str, Any]]
    scope_notes: list[str]


@dataclass(frozen=True)
class BuildResult:
    """Saída do Writer: onde o grafo foi promovido e sob qual digest."""

    graph_id: str
    graph_dir: Path
    graph_digest: str
    valid: bool
    report: dict[str, Any]
    mapper_output: MapperOutput | None = None
