"""1. Reader — lê artefatos Evidence V2 promovidos. Somente leitura."""
from __future__ import annotations

import json
from pathlib import Path

from genein.evidence_graph.graph_builder.parse import (
    CONTRACT_022_ARTIFACTS,
    OPTIONAL_ARTIFACTS,
    REQUIRED_JSON,
    REQUIRED_TSV,
    read_tsv,
    sha256_file,
)
from genein.evidence_graph.graph_builder.types import BuildRequest, SourceArtifacts

SUCCESS_STATUSES = frozenset({"done", "done_with_warning"})
CONTRACT_DISK_NAMES = frozenset(
    REQUIRED_TSV
    | REQUIRED_JSON
    | CONTRACT_022_ARTIFACTS
    | OPTIONAL_ARTIFACTS
    | {"SUCCESS.json", "artifact_manifest.json", "evidence_report.md", "run_state.json"}
)


def _load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} inválido: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} deve ser objeto JSON")
    return payload


def _normalize_sha(value: str) -> str:
    text = value.strip()
    return text[7:] if text.startswith("sha256:") else text


def verify_promotion(request: BuildRequest) -> list[str]:
    """Confere SUCCESS.json, artifact_manifest.json, identidade do run e digests."""
    run_dir = request.run_dir.resolve()
    errors: list[str] = []

    success_path = run_dir / "SUCCESS.json"
    manifest_path = run_dir / "artifact_manifest.json"
    if not success_path.is_file():
        errors.append("SUCCESS.json ausente — execução não promovida")
        return errors
    if not manifest_path.is_file():
        errors.append("artifact_manifest.json ausente")
        return errors

    try:
        success = _load_json(success_path)
    except ValueError as exc:
        errors.append(str(exc))
        return errors

    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")

        def _detect_dup_keys(pairs: list[tuple[str, object]]) -> dict:
            seen: set[str] = set()
            out: dict = {}
            for key, value in pairs:
                if key in seen:
                    raise ValueError(f"chave duplicada no manifesto: {key}")
                seen.add(key)
                out[key] = value
            return out

        manifest = json.loads(manifest_text, object_pairs_hook=_detect_dup_keys)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"artifact_manifest.json inválido: {exc}")
        return errors
    if not isinstance(manifest, dict):
        errors.append("artifact_manifest.json deve ser objeto JSON")
        return errors

    files = manifest.get("files")
    if not isinstance(files, dict):
        errors.append("artifact_manifest.json sem mapa files")
        return errors

    status = success.get("status")
    if status not in SUCCESS_STATUSES:
        errors.append(f"SUCCESS.status inválido para promoção: {status!r}")

    success_run_id = success.get("run_id")
    if not isinstance(success_run_id, str) or not success_run_id.strip():
        errors.append("SUCCESS.run_id ausente")

    expected_count = success.get("artifact_count")
    if expected_count != len(files):
        errors.append(
            f"SUCCESS.artifact_count diverge do manifesto: {expected_count} != {len(files)}"
        )

    expected_manifest_sha = success.get("artifact_manifest_sha256")
    if not isinstance(expected_manifest_sha, str) or not expected_manifest_sha:
        errors.append("SUCCESS.artifact_manifest_sha256 ausente")
    else:
        actual_manifest_sha = sha256_file(manifest_path)
        if _normalize_sha(expected_manifest_sha) != actual_manifest_sha:
            errors.append("SUCCESS.artifact_manifest_sha256 diverge do manifesto")

    for name in sorted(REQUIRED_TSV | REQUIRED_JSON):
        if name not in files:
            errors.append(f"artefato obrigatório ausente do manifesto: {name}")

    mapper_source_version = success.get("mapper_source_version")
    if mapper_source_version == "0.2.2":
        for name in sorted(CONTRACT_022_ARTIFACTS):
            if name not in files:
                errors.append(
                    f"contrato 0.2.2 incompleto: {name} obrigatório quando "
                    "mapper_source_version=0.2.2"
                )

    # Bind SUCCESS.run_id to sample_evidence / provenance when present on disk/manifest.
    identity_sources: list[str] = []
    for identity_name in ("sample_evidence.json", "provenance.json", "run_state.json"):
        if identity_name not in files:
            continue
        identity_path = run_dir / identity_name
        if not identity_path.is_file():
            continue
        try:
            doc = _load_json(identity_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        doc_run = doc.get("run_id")
        if isinstance(doc_run, str) and doc_run.strip():
            identity_sources.append(doc_run.strip())
            if isinstance(success_run_id, str) and doc_run.strip() != success_run_id.strip():
                errors.append(
                    f"run_id estrangeiro: {identity_name}={doc_run!r} != SUCCESS={success_run_id!r}"
                )

    for relative, meta in files.items():
        if not isinstance(relative, str) or not isinstance(meta, dict):
            errors.append(f"entrada inválida no manifesto: {relative!r}")
            continue
        if ".." in Path(relative).parts or relative.startswith(("/", "\\")):
            errors.append(f"path traversal no manifesto: {relative}")
            continue
        path = (run_dir / relative).resolve()
        try:
            path.relative_to(run_dir)
        except ValueError:
            errors.append(f"artefato escapa do run_dir: {relative}")
            continue
        if not path.is_file():
            errors.append(f"artefato declarado ausente no disco: {relative}")
            continue
        expected_sha = meta.get("sha256")
        if not isinstance(expected_sha, str) or not expected_sha:
            errors.append(f"sha256 ausente no manifesto: {relative}")
            continue
        actual_sha = sha256_file(path)
        if _normalize_sha(expected_sha) != actual_sha:
            errors.append(f"digest divergente: {relative}")
        if "size" not in meta:
            errors.append(f"tamanho ausente no manifesto: {relative}")
        else:
            expected_size = meta.get("size")
            if not isinstance(expected_size, int) or expected_size < 0:
                errors.append(f"tamanho inválido no manifesto: {relative}")
            elif path.stat().st_size != expected_size:
                errors.append(f"tamanho divergente: {relative}")

    # Undeclared contract artifacts on disk.
    for path in sorted(run_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name in CONTRACT_DISK_NAMES and name not in files and name not in {
            "SUCCESS.json", "artifact_manifest.json",
        }:
            # SUCCESS/manifest are commit metadata, not in files map by design in some layouts;
            # still flag other contract names sitting undeclared.
            if name in (REQUIRED_TSV | REQUIRED_JSON | CONTRACT_022_ARTIFACTS | OPTIONAL_ARTIFACTS | {"evidence_report.md", "run_state.json"}):
                errors.append(f"artefato de contrato não declarado no manifesto: {name}")

    return errors


def read(request: BuildRequest) -> SourceArtifacts:
    """Carrega somente artefatos declarados no manifesto (opcionais não auto-carregados)."""
    run_dir = request.run_dir.resolve()
    errors = verify_promotion(request)
    if errors:
        raise ValueError("; ".join(errors))

    manifest = _load_json(run_dir / "artifact_manifest.json")
    digests = manifest["files"]
    success = _load_json(run_dir / "SUCCESS.json")

    tables: dict[str, list[dict[str, str]]] = {}
    documents: dict[str, dict] = {"SUCCESS.json": success}

    for relative in digests:
        path = run_dir / relative
        try:
            if relative.endswith(".tsv"):
                tables[relative] = read_tsv(path)
            elif relative.endswith(".json") and relative != "artifact_manifest.json":
                documents[relative] = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"artefato malformado: {relative}: {exc}") from exc

    success_run_id = str(success.get("run_id") or "").strip()
    sample = documents.get("sample_evidence.json", {})
    provenance = documents.get("provenance.json", {})
    run_id = success_run_id or str(
        sample.get("run_id") or provenance.get("run_id") or run_dir.name
    )

    return SourceArtifacts(
        run_id=run_id,
        run_dir=run_dir,
        digests=digests,
        tables=tables,
        documents=documents,
    )
