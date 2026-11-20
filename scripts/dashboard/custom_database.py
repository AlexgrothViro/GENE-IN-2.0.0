"""Bind the panel's custom query to the selected, prepared database."""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re

from genein.paths import resolve_blast_db
from verify_blast_database_manifest import verify


def custom_blast_prefix(repo_root: Path) -> Path:
    selected = resolve_blast_db("custom", os.environ, Path.home(), repo_root, os.environ.get("BLAST_DB", ""))
    return (repo_root / Path(selected).expanduser()).resolve()


def _json_object(data: bytes) -> dict:
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("Esperado um objeto nos metadados do banco.")
    return payload


def _legacy_query_source(prefix: Path, manifest: dict, repo_root: Path) -> dict:
    """Read older metadata only when its index receipt matches this generation."""
    metadata = _json_object((repo_root / "db/custom/metadata.json").read_bytes())
    index_receipt = prefix.with_name(prefix.name + ".index-manifest.json")
    if metadata.get("db") != "custom" or (repo_root / Path(metadata["index_manifest"])).resolve() != index_receipt:
        raise ValueError("O recibo antigo pertence a outro prefixo.")
    reference = _json_object(index_receipt.read_bytes())["reference"]
    source = manifest["source_fasta"]
    digest = source["sha256"]
    size = source["size"]
    if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(size) is not int or size <= 0
            or reference["sha256"] != digest or reference["size"] != size):
        raise ValueError("O recibo antigo não corresponde à referência desta geração.")
    if datetime.fromisoformat(metadata["updated_at"]).timestamp() < datetime.fromisoformat(manifest["created_at"]).timestamp():
        raise ValueError("O recibo antigo foi gravado antes desta geração.")
    return {"query": metadata["db_query"], "ncbi_db": metadata["ncbi_db"]}


def custom_database_env(params: dict, prefix: Path, repo_root: Path) -> dict[str, str]:
    manifest_path = prefix.with_name(prefix.name + ".db-manifest.json")
    try:
        raw = manifest_path.read_bytes()
        manifest = _json_object(raw)
        digest = hashlib.sha256(raw).hexdigest()
        verify(prefix, manifest_path, check_hashes=False, expected_sha256=digest)
        origin = manifest["query_source"] if "query_source" in manifest else _legacy_query_source(prefix, manifest, repo_root)
        query, collection = origin["query"], origin["ncbi_db"]
        if not all(isinstance(value, str) and value.strip() for value in (query, collection)):
            raise ValueError("A origem da consulta está incompleta.")
        query, collection = query.strip(), collection.strip()
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        raise ValueError("A consulta do índice customizado não pôde ser confirmada. Prepare o banco antes de iniciar a análise.") from error

    requested_query = str(params.get("db_query") or params.get("query") or "").strip()
    requested_collection = str(params.get("ncbi_db") or "").strip()
    if (requested_query and requested_query != query) or (requested_collection and requested_collection != collection):
        raise ValueError("A consulta ou coleção NCBI selecionada difere da registrada no índice customizado. Prepare o banco para essa seleção antes de iniciar.")
    return {
        "BLAST_DB": str(prefix), "DB_QUERY": query, "NCBI_DB": collection,
        "GENEIN_EXPECTED_BLAST_MANIFEST_SHA256": digest,
    }
