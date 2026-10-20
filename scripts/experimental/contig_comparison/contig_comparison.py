#!/usr/bin/env python3
"""Transactional, experimental comparison of registered contigs against a BLAST database.

This module deliberately remains outside Evidence V2.  It records local alignments and
their provenance, but does not classify biological presence or taxonomic identity.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_ROOT = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(SCRIPTS_ROOT / "lib"))
sys.path.insert(0, str(SCRIPTS_ROOT / "evidence"))

from input_validation import iter_fasta, validate_fasta, validate_run_id, validate_sample_id
from common import fsync_directory, fsync_file, sha256_file, write_json_atomic, write_text_atomic
from finalize_panel import REQUIRED_CATEGORIES


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{7,127}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
NUCLEOTIDE_RE = re.compile(r"^[ACGTURYSWKMBDHVN.-]+$", re.IGNORECASE)
HIT_FIELDS = [
    "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
    "qstart", "qend", "sstart", "send", "evalue", "bitscore", "qlen", "slen",
    "nident", "gaps",
]
ARTIFACT_TYPES = {
    "hits": "hits.tsv", "summary": "hits_summary.tsv", "hit_contigs": "hit_contigs.fasta",
    "manifest": "comparison_manifest.json", "parameters": "blast_parameters.json",
    "source": "contigs_source.json", "reference": "reference_manifest.json",
    "provenance": "provenance.json", "state": "run_state.json", "success": "SUCCESS.json",
}
RUN_SOURCE_ARTIFACTS = {
    "metadata.json", "blast.tsv", "labeled_hits.tsv", "adj_identity.tsv",
    "hit_contigs.fasta", "assembly_contigs.fa", "report.md", "advanced_report.md",
    "assembly_summary.json", "run.log", "advanced_alignment.fa", "advanced_tree.nwk",
    "advanced_gate.json", "advanced_hits.fa", "advanced_refs.fa", "advanced_summary.tsv",
}
LOCAL_SOURCE_ARTIFACTS = {"contigs.fasta"}
COMPARISON_ARTIFACTS = {
    "contigs_source.json", "reference_manifest.json", "blast_parameters.json", "hits.tsv",
    "hits_summary.tsv", "hit_contigs.fasta", "run_state.json", "provenance.json",
}
_CUSTOM_LOCKS_GUARD = threading.Lock()
_CUSTOM_LOCKS: dict[str, threading.Lock] = {}


class ComparisonCancelled(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: str, label: str) -> str:
    value = (value or "").strip()
    if not SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{label} invalido: use 8-128 caracteres ASCII alfanumericos, '.', '_' ou '-'")
    return value


def safe_name(value: str, label: str) -> str:
    value = (value or "").strip()
    if not SAFE_NAME_RE.fullmatch(value):
        raise ValueError(f"{label} invalido: use 1-80 caracteres ASCII alfanumericos, '.', '_' ou '-'")
    return value


def _read_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} ausente ou invalido: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} deve ser um objeto JSON")
    return value


def validate_nucleotide_fasta(path: Path) -> tuple[int, int]:
    count = validate_fasta(path)
    total = 0
    for identifier, sequence in iter_fasta(path):
        if not NUCLEOTIDE_RE.fullmatch(sequence):
            raise ValueError(f"FASTA contem caracteres nao nucleotidicos na sequencia {identifier}")
        total += len(sequence)
    return count, total


def _validate_artifact_set(
    directory: Path, artifacts: object, *, required: set[str], allowed: set[str] | None = None,
) -> None:
    if not isinstance(artifacts, dict):
        raise ValueError("manifesto deve declarar artefatos com size e sha256")
    declared = set(artifacts)
    if not required.issubset(declared):
        raise ValueError("manifesto nao declara todos os artefatos obrigatorios")
    if allowed is not None and not declared.issubset(allowed):
        raise ValueError("manifesto declara artefato fora do contrato fechado")
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name not in {
            "SUCCESS.json", "manifest.json", "source_manifest.json",
            "comparison_manifest.json", "panel_manifest.json",
        }
    }
    if actual != declared:
        raise ValueError("conjunto materializado de artefatos diverge do manifesto")
    for relative, expected in artifacts.items():
        if not isinstance(relative, str) or not isinstance(expected, dict):
            raise ValueError("entrada de artefato invalida")
        path = directory / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"artefato ausente ou symlink nao permitido: {relative}")
        if set(expected) != {"size", "sha256"}:
            raise ValueError(f"metadados de artefato incompletos: {relative}")
        if expected["size"] != path.stat().st_size or expected["sha256"] != sha256_file(path):
            raise ValueError(f"size/hash do artefato nao confere: {relative}")


def _validate_committed_directory(directory: Path, *, expected_id: str, fasta_name: str) -> tuple[dict, Path]:
    if directory.is_symlink() or directory.name != expected_id or ".staging" in directory.parts:
        raise ValueError("origem parcial/staging nao pode ser utilizada")
    success = _read_object(directory / "SUCCESS.json", "SUCCESS.json")
    if success.get("schema_version") != "1.0" or success.get("status") != "done" or success.get("id") != expected_id:
        raise ValueError("SUCCESS.json nao declara uma execucao concluida para o identificador solicitado")
    manifest_name = success.get("manifest")
    if manifest_name not in {"manifest.json", "source_manifest.json"}:
        raise ValueError("SUCCESS.json nao referencia um manifesto de origem conhecido")
    manifest_path = directory / manifest_name
    manifest = _read_object(manifest_path, "manifesto da origem")
    if sha256_file(manifest_path) != success.get("manifest_sha256"):
        raise ValueError("hash do manifesto nao confere com SUCCESS.json")
    if manifest.get("schema_version") != "1.0":
        raise ValueError("schema do manifesto da origem invalido")
    if manifest_name == "manifest.json":
        if manifest.get("run_id") != expected_id:
            raise ValueError("run_id do manifesto diverge da origem")
        required = {"metadata.json", fasta_name}
        allowed = RUN_SOURCE_ARTIFACTS
    else:
        if manifest.get("id") != expected_id or manifest.get("source_type") != "local_experimental":
            raise ValueError("identidade do manifesto local diverge da origem")
        required = LOCAL_SOURCE_ARTIFACTS
        allowed = LOCAL_SOURCE_ARTIFACTS
    _validate_artifact_set(directory, manifest.get("artifacts"), required=required, allowed=allowed)
    fasta = directory / fasta_name
    validate_nucleotide_fasta(fasta)
    return manifest, fasta


def resolve_source(repo_root: Path, source_type: str, source_id: str, sample: str) -> tuple[dict, Path]:
    sample = validate_sample_id(sample)
    source_id = safe_id(source_id, "identificador da origem")
    if source_type == "run":
        directory = repo_root / "results" / "runs" / source_id
        manifest, fasta = _validate_committed_directory(
            directory, expected_id=source_id, fasta_name="assembly_contigs.fa"
        )
        declared_sample = manifest.get("sample")
        source_run = source_id
    elif source_type == "local":
        directory = repo_root / "results" / "contig_sources" / source_id
        manifest, fasta = _validate_committed_directory(
            directory, expected_id=source_id, fasta_name="contigs.fasta"
        )
        declared_sample = manifest.get("sample")
        source_run = None
    else:
        raise ValueError("source_type invalido; use run ou local")
    if declared_sample != sample:
        raise ValueError("a amostra solicitada nao corresponde a origem registrada dos contigs")
    count, total = validate_nucleotide_fasta(fasta)
    return {
        "source_type": source_type,
        "source_id": source_id,
        "contigs_source_run": source_run,
        "sample": sample,
        "logical_path": fasta.relative_to(repo_root).as_posix(),
        "sha256": sha256_file(fasta),
        "size": fasta.stat().st_size,
        "sequence_count": count,
        "total_bases": total,
        "origin": manifest.get("declared_origin") if source_type == "local" else "completed_dashboard_run",
    }, fasta


def import_local_fasta(repo_root: Path, source_file: Path, sample: str, declared_origin: str, source_id: str) -> dict:
    sample = validate_sample_id(sample)
    source_id = safe_id(source_id, "local_fasta_id")
    declared_origin = (declared_origin or "").strip()
    if not declared_origin or len(declared_origin) > 500:
        raise ValueError("a origem declarada do FASTA local e obrigatoria (maximo 500 caracteres)")
    if source_file.is_symlink():
        raise ValueError("symlink nao e permitido como FASTA local")
    count, total = validate_nucleotide_fasta(source_file)
    root = repo_root / "results" / "contig_sources"
    staging = root / ".staging" / source_id
    final = root / source_id
    if staging.exists() or final.exists():
        raise FileExistsError("local_fasta_id ja possui artefatos")
    staging.mkdir(parents=True)
    try:
        target = staging / "contigs.fasta"
        shutil.copyfile(source_file, target, follow_symlinks=False)
        fsync_file(target)
        manifest = {
            "schema_version": "1.0", "id": source_id, "sample": sample,
            "source_type": "local_experimental", "declared_origin": declared_origin,
            "imported_at": now(), "limitations": [
                "EXPERIMENTAL", "not eligible for benchmark or biological confirmation",
            ],
            "artifacts": {
                "contigs.fasta": {"size": target.stat().st_size, "sha256": sha256_file(target)},
            },
            "sequence_count": count, "total_bases": total,
        }
        write_json_atomic(staging / "source_manifest.json", manifest)
        fsync_directory(staging)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final)
        fsync_directory(final.parent)
        success = {
            "schema_version": "1.0", "id": source_id, "status": "done",
            "manifest": "source_manifest.json",
            "manifest_sha256": sha256_file(final / "source_manifest.json"), "committed_at": now(),
        }
        write_json_atomic(final / "SUCCESS.json", success)
        fsync_directory(final)
        return {"id": source_id, "sample": sample, "sequence_count": count, "total_bases": total}
    except Exception:
        if final.exists() and not (final / "SUCCESS.json").exists():
            os.replace(final, staging)
        raise


def list_sources(repo_root: Path) -> list[dict]:
    sources: list[dict] = []
    for source_type, root, fasta_name in (
        ("run", repo_root / "results" / "runs", "assembly_contigs.fa"),
        ("local", repo_root / "results" / "contig_sources", "contigs.fasta"),
    ):
        if not root.is_dir():
            continue
        for directory in root.iterdir():
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            try:
                manifest, fasta = _validate_committed_directory(
                    directory, expected_id=directory.name, fasta_name=fasta_name
                )
            except (OSError, ValueError):
                continue
            sources.append({
                "source_type": source_type, "source_id": directory.name,
                "sample": manifest.get("sample"), "sequence_count": validate_fasta(fasta),
                "label": f"{manifest.get('sample') or '?'} · {directory.name} · {source_type}",
            })
    return sorted(sources, key=lambda item: (item.get("sample") or "", item["source_id"]))


def _state(staging: Path, comparison_id: str, status: str, *, emit: bool = True, **extra: object) -> None:
    if emit:
        print(f"[CONTIG_COMPARE][STATE] {status}", flush=True)
    current = {}
    path = staging / "run_state.json"
    if path.is_file():
        current = _read_object(path, "run_state.json")
    current.update({"comparison_id": comparison_id, "status": status, "updated_at": now(), **extra})
    write_json_atomic(path, current)


def _tool(command: str, version_args: list[str]) -> dict:
    executable = shutil.which(command)
    if not executable:
        raise RuntimeError(f"ferramenta obrigatoria indisponivel: {command}")
    result = subprocess.run([executable, *version_args], capture_output=True, text=True, check=False)
    first = (result.stdout or result.stderr).splitlines()
    return {
        "command": command, "executable": str(Path(executable).resolve()),
        "executable_sha256": sha256_file(executable), "version": first[0] if first else "UNKNOWN",
    }


def _database_reference(repo_root: Path, database: str, query: str, ncbi_db: str) -> tuple[dict, Path]:
    database = safe_name(database, "reference_database")
    environment = os.environ.copy()
    environment["DB"] = database
    if database == "custom":
        if not query.strip():
            raise ValueError("banco customizado exige query NCBI explicita")
        environment["DB_QUERY"] = query.strip()
        environment["NCBI_DB"] = (ncbi_db or "nucleotide").strip()
        environment["DB_MANAGER_LOCK_HELD"] = "1"
    subprocess.run(
        ["bash", "scripts/ops/db_manager.sh", "setup-blast"], cwd=repo_root,
        env=environment, check=True,
    )
    reference = repo_root / "data" / "ref" / f"{database}.fa"
    prefix = repo_root / "blastdb" / database
    validate_nucleotide_fasta(reference)
    subprocess.run(["blastdbcmd", "-db", str(prefix), "-info"], check=True, capture_output=True, text=True)
    index_files = sorted(
        path for path in prefix.parent.glob(prefix.name + ".*")
        if path.is_file() and not path.name.endswith((".json", ".lock"))
    )
    if not index_files:
        raise ValueError("banco BLAST nao possui indices materializados")
    generation_path = repo_root / "blastdb" / f"{database}.db-manifest.json"
    manager_path = repo_root / "scripts" / "ops" / "db_manager.sh"
    return {
        "reference_kind": "database", "reference_database": database,
        "query": query.strip() if database == "custom" else None,
        "ncbi_database": (ncbi_db or "nucleotide").strip() if database == "custom" else None,
        "reference_fasta": reference.relative_to(repo_root).as_posix(),
        "reference_fasta_sha256": sha256_file(reference),
        "blast_prefix": prefix.relative_to(repo_root).as_posix(),
        "index_files": {
            path.relative_to(repo_root).as_posix(): {"size": path.stat().st_size, "sha256": sha256_file(path)}
            for path in index_files
        },
        "generation_manifest": (
            {"path": generation_path.relative_to(repo_root).as_posix(), "sha256": sha256_file(generation_path)}
            if generation_path.is_file() else None
        ),
        "preparation": {
            "manager": {"path": "scripts/ops/db_manager.sh", "sha256": sha256_file(manager_path)},
            "makeblastdb": _tool("makeblastdb", ["-version"]),
        },
    }, prefix


@contextmanager
def _custom_database_lease(repo_root: Path):
    lock_path = repo_root / "tmp" / "db-manager.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    key = str(lock_path.resolve())
    with _CUSTOM_LOCKS_GUARD:
        thread_lock = _CUSTOM_LOCKS.setdefault(key, threading.Lock())
    with thread_lock:
        handle = lock_path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                while True:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def _blast_database_sequences(prefix: Path) -> dict[str, str]:
    result = subprocess.run(
        ["blastdbcmd", "-db", str(prefix), "-entry", "all", "-outfmt", "%i\t%s"],
        check=True, capture_output=True, text=True,
    )
    sequences: dict[str, str] = {}
    for line in result.stdout.splitlines():
        identifier, separator, sequence = line.partition("\t")
        if not separator:
            raise ValueError("blastdbcmd retornou sequencia sem identificador")
        if identifier.startswith("lcl|"):
            identifier = identifier[4:]
        if identifier in sequences:
            raise ValueError("BLAST DB possui identificador duplicado")
        sequences[identifier] = sequence.upper()
    return sequences


def _panel_reference(repo_root: Path, panel_id: str) -> tuple[dict, Path]:
    panel_id = safe_name(panel_id, "panel_id")
    directory = repo_root / "results" / "evidence" / "panels" / panel_id
    if directory.is_symlink():
        raise ValueError("symlink nao e permitido como painel competitivo")
    success = _read_object(directory / "SUCCESS.json", "SUCCESS.json do painel")
    manifest = _read_object(directory / "panel_manifest.json", "manifesto do painel")
    if success.get("status") != "done" or success.get("panel_id") != panel_id or success.get("manifest") != "panel_manifest.json":
        raise ValueError("painel competitivo nao esta concluido")
    if success.get("manifest_sha256") != sha256_file(directory / "panel_manifest.json"):
        raise ValueError("manifesto do painel nao confere com SUCCESS.json")
    if manifest.get("schema_version") != "2.0" or manifest.get("panel_id") != panel_id:
        raise ValueError("identidade/schema do manifesto do painel invalido")
    files = manifest.get("files")
    blast_required = {f"blast/panel.{extension}" for extension in ("nhr", "nin", "nsq")}
    bt2 = {f"bowtie2/panel.{extension}.bt2" for extension in ("1", "2", "3", "4", "rev.1", "rev.2")}
    bt2l = {f"bowtie2/panel.{extension}.bt2l" for extension in ("1", "2", "3", "4", "rev.1", "rev.2")}
    declared = set(files) if isinstance(files, dict) else set()
    bowtie_required = bt2 if bt2.issubset(declared) else bt2l
    if not bowtie_required.issubset(declared):
        raise ValueError("painel competitivo nao possui indice Bowtie2 completo")
    required = {"panel.fa", "labels.tsv", *blast_required, *bowtie_required}
    _validate_artifact_set(directory, files, required=required)
    sequences = dict(iter_fasta(directory / "panel.fa"))
    if manifest.get("sequence_count") != len(sequences):
        raise ValueError("sequence_count do painel diverge do FASTA")
    with (directory / "labels.tsv").open("r", encoding="utf-8", newline="") as handle:
        labels = list(csv.DictReader(handle, delimiter="\t"))
    if {row.get("sseqid") for row in labels} != set(sequences):
        raise ValueError("labels.tsv nao corresponde aos sujeitos do painel")
    categories = {row.get("category") for row in labels}
    if not REQUIRED_CATEGORIES.issubset(categories) or set(manifest.get("categories") or []) != categories:
        raise ValueError("categorias do painel estao incompletas ou divergentes")
    prefix = directory / "blast" / "panel"
    subprocess.run(["blastdbcmd", "-db", str(prefix), "-info"], check=True, capture_output=True, text=True)
    indexed_sequences = _blast_database_sequences(prefix)
    if {key: value.upper() for key, value in sequences.items()} != indexed_sequences:
        raise ValueError("BLAST DB do painel diverge do FASTA promovido")
    return {
        "reference_kind": "competitive_panel", "reference_database": panel_id,
        "panel_manifest_sha256": sha256_file(directory / "panel_manifest.json"),
        "reference_fasta": (directory / "panel.fa").relative_to(repo_root).as_posix(),
        "reference_fasta_sha256": sha256_file(directory / "panel.fa"),
        "blast_prefix": prefix.relative_to(repo_root).as_posix(),
        "index_files": manifest.get("files", {}),
        "preparation": {"constructors": manifest.get("constructors", {})},
        "subject_count": len(sequences),
    }, prefix


def _write_derived(staging: Path, fasta: Path) -> None:
    rows: list[dict[str, str]] = []
    with (staging / "hits.tsv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HIT_FIELDS:
            raise ValueError("cabecalho de hits.tsv invalido")
        rows = list(reader)
    by_query: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_query.setdefault(row["qseqid"], []).append(row)
    summary_lines = ["qseqid\thit_count\tbest_bitscore\tbest_evalue\tcompatible_subjects"]
    for query_id in sorted(by_query):
        hits = by_query[query_id]
        best = max(hits, key=lambda row: float(row["bitscore"]))
        subjects = ";".join(sorted({row["sseqid"] for row in hits}))
        summary_lines.append(f"{query_id}\t{len(hits)}\t{best['bitscore']}\t{best['evalue']}\t{subjects}")
    write_text_atomic(staging / "hits_summary.tsv", "\n".join(summary_lines) + "\n")
    wanted = set(by_query)
    fasta_lines: list[str] = []
    for identifier, sequence in iter_fasta(fasta):
        if identifier in wanted:
            fasta_lines.extend((f">{identifier}", sequence))
    write_text_atomic(staging / "hit_contigs.fasta", ("\n".join(fasta_lines) + "\n") if fasta_lines else "")


def execute(args: argparse.Namespace) -> Path:
    repo_root = args.repo_root.resolve()
    comparison_id = validate_run_id(args.comparison_id)
    sample = validate_sample_id(args.sample)
    task = args.blast_task
    if task not in {"blastn", "blastn-short"}:
        raise ValueError("blast_task deve ser blastn ou blastn-short")
    ranges = {"word_size": (4, 1000), "max_target_seqs": (1, 1000000), "threads": (1, 256)}
    for name, (minimum, maximum) in ranges.items():
        value = getattr(args, name)
        if value < minimum or value > maximum:
            raise ValueError(f"{name} fora do intervalo permitido ({minimum}-{maximum})")
    if not (0 < args.evalue <= 1_000_000):
        raise ValueError("evalue deve ser maior que zero e no maximo 1000000")

    source, fasta = resolve_source(repo_root, args.source_type, args.source_id, sample)
    prevalidated_panel = None
    if args.reference_kind == "panel":
        # A partial/tampered panel is rejected before operational staging exists.
        prevalidated_panel = _panel_reference(repo_root, args.database)

    root = repo_root / "results" / "contig_comparisons"
    staging = root / ".staging" / comparison_id
    final = root / comparison_id
    if staging.exists() or final.exists():
        raise FileExistsError("comparison_id ja possui staging ou resultado final")
    staging.mkdir(parents=True)
    _state(staging, comparison_id, "validating_contigs", sample=sample)
    write_json_atomic(staging / "contigs_source.json", source)

    _state(staging, comparison_id, "preparing_database")
    custom_database = args.reference_kind == "database" and args.database == "custom"
    lease = _custom_database_lease(repo_root) if custom_database else nullcontext()
    with lease:
        if prevalidated_panel is not None:
            reference, blast_prefix = prevalidated_panel
        else:
            reference, blast_prefix = _database_reference(repo_root, args.database, args.db_query, args.ncbi_db)
        write_json_atomic(staging / "reference_manifest.json", reference)

        effective_max_targets = args.max_target_seqs
        if args.reference_kind == "panel":
            effective_max_targets = max(args.max_target_seqs, int(reference["subject_count"]))
        parameters = {
            "blast_task": task, "word_size": args.word_size, "evalue": args.evalue,
            "requested_max_target_seqs": args.max_target_seqs,
            "effective_max_target_seqs": effective_max_targets,
            "panel_subject_count": reference.get("subject_count"),
            "threads": args.threads, "outfmt_fields": HIT_FIELDS,
        }
        write_json_atomic(staging / "blast_parameters.json", parameters)
        blast = _tool("blastn", ["-version"])
        _state(staging, comparison_id, "running_blast")
        raw = staging / ".hits.raw.tmp"
        command = [
            blast["executable"], "-task", task, "-query", str(fasta), "-db", str(blast_prefix),
            "-word_size", str(args.word_size), "-evalue", str(args.evalue),
            "-max_target_seqs", str(effective_max_targets), "-num_threads", str(args.threads),
            "-outfmt", "6 " + " ".join(HIT_FIELDS), "-out", str(raw),
        ]
        subprocess.run(command, cwd=repo_root, check=True)
        with raw.open("r", encoding="utf-8", errors="strict") as source_handle:
            body = source_handle.read()
    write_text_atomic(staging / "hits.tsv", "\t".join(HIT_FIELDS) + "\n" + body)
    raw.unlink()
    _write_derived(staging, fasta)
    provenance = {
        "schema_version": "1.0", "comparison_id": comparison_id, "created_at": now(),
        "blast": blast, "command": command[:-2] + ["-out", "<staging>/hits.raw"],
        "runner": {"path": "scripts/experimental/contig_comparison/contig_comparison.py", "sha256": sha256_file(Path(__file__))},
        "interpretation": "local sequence alignments and local homology only",
        "not_evidence_v2": True,
    }
    write_json_atomic(staging / "provenance.json", provenance)

    _state(staging, comparison_id, "promoting")
    _state(staging, comparison_id, "done", emit=False, completed_at=now())
    required = sorted(COMPARISON_ARTIFACTS)
    for name in required:
        path = staging / name
        if not path.is_file():
            raise ValueError(f"artefato obrigatorio ausente: {name}")
        fsync_file(path)
    manifest = {
        "schema_version": "1.0", "comparison_id": comparison_id, "sample": sample,
        "contigs_source_run": source.get("contigs_source_run"), "contigs_source_id": source["source_id"],
        "contigs_source": source,
        "reference_database": reference["reference_database"],
        "reference_kind": reference["reference_kind"], "reference": reference,
        "blast_parameters": parameters, "tool_versions": {"blastn": blast}, "status": "done",
        "created_at": provenance["created_at"], "completed_at": now(),
        "interpretation": "alinhamentos compativeis, hits e homologia local",
        "limitations": ["not Evidence V2", "no biological presence confirmation", "no taxonomic identification"],
        "artifacts": {
            name: {"size": (staging / name).stat().st_size, "sha256": sha256_file(staging / name)}
            for name in required
        },
    }
    write_json_atomic(staging / "comparison_manifest.json", manifest)
    fsync_directory(staging)
    final.parent.mkdir(parents=True, exist_ok=True)
    if staging.stat().st_dev != final.parent.stat().st_dev:
        raise ValueError("staging e destino final devem compartilhar o filesystem")
    os.replace(staging, final)
    fsync_directory(final.parent)
    try:
        success = {
            "schema_version": "1.0", "id": comparison_id, "comparison_id": comparison_id,
            "status": "done", "manifest": "comparison_manifest.json",
            "manifest_sha256": sha256_file(final / "comparison_manifest.json"), "committed_at": now(),
        }
        write_json_atomic(final / "SUCCESS.json", success)
        fsync_directory(final)
    except Exception:
        (final / "SUCCESS.json").unlink(missing_ok=True)
        os.replace(final, staging)
        raise
    print(f"[CONTIG_COMPARE][STATE] done", flush=True)
    print(final, flush=True)
    return final


def validate_comparison(directory: Path) -> dict:
    if directory.is_symlink():
        raise ValueError("symlink nao e permitido como comparacao")
    success = _read_object(directory / "SUCCESS.json", "SUCCESS.json da comparacao")
    manifest = _read_object(directory / "comparison_manifest.json", "manifesto da comparacao")
    if (
        success.get("schema_version") != "1.0" or success.get("status") != "done"
        or success.get("id") != directory.name or success.get("comparison_id") != directory.name
        or success.get("manifest") != "comparison_manifest.json"
    ):
        raise ValueError("comparacao nao esta concluida")
    if success.get("manifest_sha256") != sha256_file(directory / "comparison_manifest.json"):
        raise ValueError("hash do manifesto da comparacao nao confere")
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("comparison_id") != directory.name
        or manifest.get("status") != "done"
    ):
        raise ValueError("identidade/schema/status do manifesto da comparacao invalido")
    _validate_artifact_set(
        directory, manifest.get("artifacts"),
        required=COMPARISON_ARTIFACTS, allowed=COMPARISON_ARTIFACTS,
    )
    return manifest


def finalize_contig_comparison_cancellation(repo_root: Path, comparison_id: str, message: str) -> dict:
    comparison_id = validate_run_id(comparison_id)
    root = repo_root.resolve() / "results" / "contig_comparisons"
    staging = root / ".staging" / comparison_id
    final = root / comparison_id
    cancelled = root / ".cancelled" / comparison_id
    state_path = root / "state" / f"{comparison_id}.json"
    if (final / "SUCCESS.json").is_file():
        raise ValueError("comparacao valida promovida nao pode ser cancelada")
    candidate = staging if staging.exists() else final if final.exists() else None
    if candidate is not None:
        if candidate.is_symlink() or candidate.name != comparison_id:
            raise ValueError("diretorio parcial de cancelamento invalido")
        candidate.resolve().relative_to(root.resolve())
        if cancelled.exists():
            raise FileExistsError("registro de cancelamento ja existe")
        _state(
            candidate, comparison_id, "cancelled", emit=False,
            finished_at=now(), failure_type="CANCELLED", failure_message=message,
        )
        cancelled.parent.mkdir(parents=True, exist_ok=True)
        os.replace(candidate, cancelled)
        fsync_directory(cancelled.parent)
    record = {
        "schema_version": "1.0", "comparison_id": comparison_id, "status": "cancelled",
        "finished_at": now(), "failure_type": "CANCELLED", "failure_message": message,
        "cancelled_artifacts": (
            cancelled.relative_to(repo_root.resolve()).as_posix() if cancelled.exists() else None
        ),
        "staging_cleared": not staging.exists() and not final.exists(),
    }
    write_json_atomic(state_path, record)
    return record


def list_comparisons(repo_root: Path) -> list[dict]:
    root = repo_root / "results" / "contig_comparisons"
    result = []
    if not root.is_dir():
        return result
    for directory in root.iterdir():
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        try:
            manifest = validate_comparison(directory)
        except (OSError, ValueError):
            continue
        result.append({**manifest, "run_dir": directory.name, "action": "compare_contigs"})
    return sorted(result, key=lambda item: item.get("completed_at", ""), reverse=True)


def comparison_artifact(repo_root: Path, comparison_id: str, artifact_type: str) -> Path:
    comparison_id = safe_id(comparison_id, "comparison_id")
    filename = ARTIFACT_TYPES.get(artifact_type)
    if not filename:
        raise ValueError("tipo de artefato da comparacao invalido")
    directory = repo_root / "results" / "contig_comparisons" / comparison_id
    validate_comparison(directory)
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(f"artefato ausente: {artifact_type}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    run_parser.add_argument("--comparison-id", required=True)
    run_parser.add_argument("--sample", required=True)
    run_parser.add_argument("--source-type", choices=["run", "local"], required=True)
    run_parser.add_argument("--source-id", required=True)
    run_parser.add_argument("--reference-kind", choices=["database", "panel"], default="database")
    run_parser.add_argument("--database", required=True)
    run_parser.add_argument("--db-query", default="")
    run_parser.add_argument("--ncbi-db", default="nucleotide")
    run_parser.add_argument("--blast-task", choices=["blastn", "blastn-short"], default="blastn")
    run_parser.add_argument("--word-size", type=int, default=11)
    run_parser.add_argument("--evalue", type=float, default=1e-5)
    run_parser.add_argument("--max-target-seqs", type=int, default=50)
    run_parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def _cancel_signal(_signum, _frame):
        raise ComparisonCancelled("processo de comparacao recebeu SIGTERM")

    signal.signal(signal.SIGTERM, _cancel_signal)
    try:
        execute(args)
        return 0
    except ComparisonCancelled as exc:
        finalize_contig_comparison_cancellation(
            args.repo_root.resolve(), args.comparison_id, str(exc),
        )
        print(f"[CONTIG_COMPARE][CANCELLED] {exc}", file=sys.stderr)
        return 130
    except Exception as exc:
        try:
            comparison_id = validate_run_id(getattr(args, "comparison_id", ""))
            staging = args.repo_root.resolve() / "results" / "contig_comparisons" / ".staging" / comparison_id
            if staging.is_dir() and not staging.is_symlink():
                _state(staging, comparison_id, "failed", failure_message=str(exc))
        except (OSError, ValueError):
            pass
        print(f"[CONTIG_COMPARE][ERROR] {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())
