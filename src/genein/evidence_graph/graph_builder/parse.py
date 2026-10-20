"""Parsing factual e regras versionadas para o Mapper v0.2.2."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAPPER_VERSION = "0.2.2"
RULE_CATALOG_VERSION = "rule-catalog:0.1"
SCHEMA_VERSION = "0.2"

# Enum fechado — conversão só quando o artefato declara explicitamente.
ALLOWED_COORD_SYSTEMS = frozenset({"1-based-inclusive"})
ALLOWED_STRANDS = frozenset({"+", "-", "plus", "minus"})

# Colunas canônicas de hsp_evidence.tsv (uma linha = um HSP real).
HSP_EVIDENCE_COLUMNS = (
    "hsp_id",
    "duplicate_of_hsp_id",
    "qseqid",
    "sseqid",
    "task",
    "query_start",
    "query_end",
    "subject_start",
    "subject_end",
    "alignment_length",
    "identity_pct",
    "matches",
    "mismatches",
    "gaps",
    "gap_openings",
    "evalue",
    "bitscore",
    "strand",
    "coord_system",
    "query_length",
    "subject_length",
    "locus_id",
    "eligible",
    "rejection_reason",
    "rule_id",
)

TEMPLATE_LINEAGE_COLUMNS = (
    "lineage_record_id",
    "lineage_id",
    "sample_id",
    "reference_id",
    "locus_id",
    "orientation",
    "query_ids",
    "source_template_digests",
    "final_umi",
    "umi_group_method",
    "library_mode",
    "umi_mode",
    "template_count",
    "read_count",
    "mapped_bases",
    "proper_pair_templates",
    "discordant_templates",
    "eligible",
    "rejection_reason",
    "rule_id",
)

REQUIRED_TSV = frozenset({
    "fragment_evidence.tsv",
    "locus_evidence.tsv",
    "competitive_hits.tsv",
    "read_support.tsv",
    "coverage.tsv",
})
REQUIRED_JSON = frozenset({
    "sample_evidence.json",
    "provenance.json",
    "runtime_preflight.json",
})
# Sidecars do contrato 0.2.2 — obrigatórios somente quando SUCCESS declara a versão.
CONTRACT_022_ARTIFACTS = frozenset({"hsp_evidence.tsv", "template_lineage.tsv"})
OPTIONAL_ARTIFACTS = frozenset({
    "hsp_evidence.tsv",
    "template_lineage.tsv",
    "assembly_concordance.tsv",
    "assembly_concordance.json",
})

_INTERVAL_RE = re.compile(r"^(\d+)-(\d+)$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parameters_digest(parameters: Any) -> str:
    payload = json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{sha256_text(payload)}"


def digest_ref(digests: dict[str, dict[str, Any]], source_ref: str) -> str:
    """Resolve sha256 citável; falha se o artefato ou o digest forem inválidos."""
    if source_ref not in digests:
        raise ValueError(f"artefato ausente do mapa de digests: {source_ref}")
    entry = digests[source_ref]
    if not isinstance(entry, dict):
        raise ValueError(f"digest malformado: {source_ref}")
    raw = entry.get("sha256")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"digest malformado: {source_ref}")
    hex_part = raw[7:] if raw.startswith("sha256:") else raw
    if not _SHA256_HEX_RE.match(hex_part):
        raise ValueError(f"digest malformado: {source_ref}")
    return f"sha256:{hex_part.lower()}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            return []
        return [dict(row) for row in reader]


def write_tsv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows or []:
            writer.writerow({col: "" if row.get(col) is None else row.get(col, "") for col in columns})


def parse_interval_token(token: str) -> tuple[int, int] | None:
    token = token.strip()
    if not token:
        return None
    match = _INTERVAL_RE.match(token)
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    if start < 1 or end < start:
        return None
    return start, end


def parse_interval_list(raw: str) -> list[dict[str, int]]:
    """Normaliza reference_intervals; rejeita a lista inteira se qualquer token for inválido."""
    if not raw or not raw.strip():
        return []
    if "," in raw:
        return []
    intervals: list[tuple[int, int]] = []
    for part in raw.split(";"):
        parsed = parse_interval_token(part)
        if parsed is None:
            return []
        intervals.append(parsed)
    intervals.sort()
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [{"start": start, "end": end} for start, end in merged]


def admit_coord_system(raw: str | None) -> tuple[str | None, bool, str | None]:
    """Retorna (valor, elegível, rejection_reason). Ausência nunca é inferida."""
    if raw is None or not str(raw).strip() or str(raw).strip().upper() == "NA":
        return None, False, "MISSING_FIELD"
    value = str(raw).strip()
    if value not in ALLOWED_COORD_SYSTEMS:
        return value, False, "INVALID_COORDINATES"
    return value, True, None


def admit_strand(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip() or str(raw).strip().upper() == "NA":
        return None
    value = str(raw).strip()
    return value if value in ALLOWED_STRANDS else None


def safe_int(raw: str | None) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    value = str(raw).strip()
    if value.upper() == "NA":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def safe_float(raw: str | None) -> float | None:
    if raw is None or not str(raw).strip():
        return None
    value = str(raw).strip()
    if value.upper() == "NA":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_bool_cell(raw: str | None) -> bool | None:
    if raw is None or not str(raw).strip() or str(raw).strip().upper() == "NA":
        return None
    value = str(raw).strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    return None


def empty_to_none(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value.upper() == "NA":
        return None
    return value


def node_id(prefix: str, key: str) -> str:
    """ID resistente a colisão: PREFIX-<slug ≤32>-<12 hex SHA-256 do valor original>."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", key)[:32].strip("_") or "x"
    return f"{prefix}-{slug}-{sha256_text(key)[:12]}"
