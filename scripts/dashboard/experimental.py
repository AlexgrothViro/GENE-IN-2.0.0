"""Descoberta somente-leitura de execuções de mapeamento direto.

Somente execuções completas, com manifesto e hashes consistentes, são exibidas.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "experimental" / "direct_map"))

from experimental_direct_map import (  # noqa: E402
    OUTPUT_CONTRACTS,
    PIPELINE_VERSION,
    PROFILE_ID,
)

# Revisao vigente derivada do perfil versionado, nunca fixada a mao.
PROFILE_REVISION = json.loads(
    (REPO_ROOT / "config" / "experimental" / "direct_map_v1.json").read_text(
        encoding="utf-8"
    )
)["profile_revision"]

# Uma execucao so e exibida como vigente quando esta integralmente promovida.
REQUIRED_FOR_CURRENT = (
    "SUCCESS.json",
    "artifact_manifest.json",
    "direct_map_metrics.json",
    "provenance.json",
    "profile.json",
    "panel_manifest.json",
    "coverage_metrics.tsv",
)

# `scripts/experimental/direct_map/run.sh` grava em `<out-root>/experimental/direct-map-v1`.
# O dashboard descobre a mesma arvore a partir da mesma out-root.
DEFAULT_EXPERIMENTAL_OUT_ROOT = REPO_ROOT / "results" / "rd"
EXPERIMENT_SUBPATH = ("experimental", "direct-map-v1", "runs")

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

PUBLIC_EVIDENCE_ROOT = Path(
    os.environ.get("GENEIN_PUBLIC_EVIDENCE_ROOT", "")
    or (REPO_ROOT / "results" / "evidence")
)

# Artefatos legiveis pelo dashboard. BAM/BAI ficam de fora: sao volumosos e nao
# acrescentam nada a visibilidade de apresentacao.
ARTIFACT_TYPES = {
    "metrics": "direct_map_metrics.json",
    "provenance": "provenance.json",
    "profile": "profile.json",
    "panel_manifest": "panel_manifest.json",
    "artifact_manifest": "artifact_manifest.json",
    "success": "SUCCESS.json",
    "coverage_metrics": "coverage_metrics.tsv",
    "read_classifications": "read_classifications.tsv",
    "template_geometry": "template_geometry.tsv",
}


def experimental_out_root():
    configured = os.environ.get("GENEIN_EXPERIMENTAL_OUT_ROOT", "").strip()
    return Path(configured).resolve() if configured else DEFAULT_EXPERIMENTAL_OUT_ROOT.resolve()


def direct_map_runs_dir():
    """Raiz das execucoes promovidas, recusada se colidir com a arvore publica."""
    out_root = experimental_out_root()
    public_root = PUBLIC_EVIDENCE_ROOT.resolve()
    if out_root == public_root or public_root in out_root.parents:
        raise ValueError(
            "a raiz experimental nao pode estar dentro da arvore publica Evidence V2"
        )
    return out_root.joinpath(*EXPERIMENT_SUBPATH)


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sha256_file(path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _run_state(run_dir, success, metrics, provenance, profile, manifest):
    """
    Classifica a execucao sem nunca reinterpreta-la.

    `current` exige execucao completa e coerente: todos os artefatos exigidos
    presentes, contratos de saida iguais aos vigentes em SUCCESS/metricas/
    proveniencia/perfil, identidade (profile_id, profile_revision,
    pipeline_version) consistente entre metricas, proveniencia e perfil, e
    `artifact_manifest.json` integro contra o hash ancorado no SUCCESS.

    Qualquer outro caso e `incomplete`, `incompatible` ou `unknown` — nunca
    `current`. Os hashes por arquivo do manifesto NAO sao reverificados aqui:
    esta e uma camada de visibilidade, nao o validador do perfil.
    """
    missing = [name for name in REQUIRED_FOR_CURRENT if not (run_dir / name).is_file()]
    if missing:
        return "incomplete", f"artefatos ausentes: {', '.join(sorted(missing))}"

    declared = [
        success.get("contract_versions"),
        metrics.get("contract_versions"),
        provenance.get("contract_versions"),
        profile.get("output_contracts"),
    ]
    if any(item is None for item in declared):
        return "unknown", "contratos de saida nao declarados em todos os artefatos"
    if any(item != OUTPUT_CONTRACTS for item in declared):
        return "incompatible", "contratos de saida divergem dos contratos vigentes"

    identities = {
        (
            item.get("profile_id"),
            item.get("profile_revision"),
            item.get("pipeline_version"),
        )
        for item in (metrics, provenance)
    }
    identities.add((
        profile.get("profile_id"),
        profile.get("profile_revision"),
        profile.get("pipeline_version"),
    ))
    if len(identities) != 1:
        return "incompatible", "identidade divergente entre metricas, proveniencia e perfil"
    identity = identities.pop()
    if identity != (PROFILE_ID, PROFILE_REVISION, PIPELINE_VERSION):
        return "incompatible", "identidade do perfil/pipeline nao e a vigente"
    if success.get("pipeline_version") != PIPELINE_VERSION:
        return "incompatible", "SUCCESS declara outro pipeline"

    anchored = success.get("artifact_manifest_sha256")
    if not anchored:
        return "unknown", "SUCCESS nao ancora o hash do manifesto de artefatos"
    if _sha256_file(run_dir / "artifact_manifest.json") != anchored:
        return "incompatible", "manifesto de artefatos nao confere com o hash do SUCCESS"
    if not isinstance(manifest.get("files"), (list, dict)):
        return "unknown", "manifesto de artefatos nao lista arquivos"

    return "current", None


def _run_summary(run_dir):
    success = _read_json(run_dir / "SUCCESS.json")
    if not isinstance(success, dict):
        return None  # execucao nao promovida: nunca exibida

    def _obj(name):
        value = _read_json(run_dir / name)
        return value if isinstance(value, dict) else {}

    metrics = _obj("direct_map_metrics.json")
    provenance = _obj("provenance.json")
    profile = _obj("profile.json")
    manifest = _obj("artifact_manifest.json")
    contract_state, state_reason = _run_state(
        run_dir, success, metrics, provenance, profile, manifest
    )
    summary = {
        "run_id": success.get("run_id") or run_dir.name,
        "status": success.get("status"),
        "completed_at": success.get("completed_at"),
        "artifact_count": success.get("artifact_count"),
        "contract_state": contract_state,
        "contract_versions": success.get("contract_versions"),
        "pipeline_version": success.get("pipeline_version"),
    }
    if contract_state == "current":
        summary.update({
            "sample_id": metrics.get("sample_id"),
            "profile_id": metrics.get("profile_id"),
            "profile_revision": metrics.get("profile_revision"),
            "input_reads": metrics.get("input_reads"),
            "input_templates": metrics.get("input_templates"),
            "invariant_state": (metrics.get("invariants") or {}).get("state"),
            "coverage_cells_measured": (metrics.get("invariants") or {}).get("coverage_cells_measured"),
            "coverage_cells_not_measured": (metrics.get("invariants") or {}).get("coverage_cells_not_measured"),
        })
    else:
        summary["note"] = (
            f"Execucao nao exibida como vigente ({contract_state}): "
            f"{state_reason}. Exibida apenas por identidade e "
            "nao reinterpretada sob o contrato vigente."
        )
    summary["artifacts"] = sorted(
        name for name, filename in ARTIFACT_TYPES.items()
        if (run_dir / filename).is_file()
    )
    return summary


def list_direct_map_runs():
    """Lista execucoes experimentais promovidas. Nunca levanta por ausencia."""
    payload = {"runs": []}
    try:
        runs_dir = direct_map_runs_dir()
    except ValueError as exc:
        return {**payload, "available": False, "root": None, "error": str(exc)}

    payload["root"] = str(runs_dir)
    if not runs_dir.is_dir():
        return {
            **payload,
            "available": False,
            "hint": (
                "Nenhuma execucao experimental encontrada. Defina "
                "GENEIN_EXPERIMENTAL_OUT_ROOT ou rode "
                "scripts/experimental/direct_map/run.sh --out-root <raiz>."
            ),
        }

    runs = []
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir() or not RUN_ID_PATTERN.match(child.name):
            continue
        summary = _run_summary(child)
        if summary:
            runs.append(summary)
    runs.sort(key=lambda item: str(item.get("completed_at") or ""), reverse=True)
    payload["runs"] = runs
    payload["available"] = True
    return payload


def _resolve_run_dir(run_id):
    run_id = str(run_id or "").strip()
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError("run_id experimental invalido")
    runs_dir = direct_map_runs_dir()
    candidate = (runs_dir / run_id).resolve()
    if candidate.parent != runs_dir.resolve() or not candidate.is_dir():
        raise FileNotFoundError(f"execucao experimental nao encontrada: {run_id}")
    if not (candidate / "SUCCESS.json").is_file():
        raise FileNotFoundError(f"execucao experimental nao promovida: {run_id}")
    return candidate


def direct_map_run(run_id):
    run_dir = _resolve_run_dir(run_id)
    summary = _run_summary(run_dir)
    if not summary:
        raise FileNotFoundError(f"execucao experimental nao promovida: {run_id}")
    return {"run": summary}


def direct_map_artifact(run_id, artifact_type):
    run_dir = _resolve_run_dir(run_id)
    filename = ARTIFACT_TYPES.get(str(artifact_type or "").strip())
    if not filename:
        raise ValueError("tipo de artefato experimental invalido")
    target = (run_dir / filename).resolve()
    if target.parent != run_dir or not target.is_file():
        raise FileNotFoundError(f"artefato experimental nao encontrado: {artifact_type}")
    return target
