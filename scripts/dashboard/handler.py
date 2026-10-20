"""
Gene-In Dashboard HTTP Handler Module
Manipulador HTTP de requisições, endpoints REST, upload de arquivos e arquivos estáticos.
"""

import email
import email.parser
import email.policy
import hashlib
import html
import json
import logging
import os
import shutil
import signal
import sys
import tempfile
import traceback
import uuid
import zipfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from logging.handlers import RotatingFileHandler


def query_one(query, key):
    """Return a single query value or fail closed on duplicates."""
    values = query.get(key) or []
    if len(values) > 1:
        raise ValueError(f"parâmetro duplicado: {key}")
    return values[0] if values else ""

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "experimental" / "contig_comparison"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from input_validation import validate_fastq, validate_sample_id
from evidence_dashboard import EvidenceDashboardService, atomic_json
from dashboard.config import (
    DASHBOARD_DIR, LOG_DIR, RUNS_DIR, REPO_ROOT, INSTALL_WSL_SCRIPT,
    JAVASCRIPT_MODULES, SUPPORTED_ENV_KEYS, get_preflight_status,
    list_targets, list_db_profiles, load_config_env, validate_config_updates,
    save_config_env, validate_host_index, get_environment_status, require_sample_id,
)
from dashboard.experimental import (
    direct_map_artifact, direct_map_run, list_direct_map_runs,
)
from contig_comparison import (
    comparison_artifact, finalize_contig_comparison_cancellation,
    import_local_fasta, list_comparisons, list_sources,
)
from dashboard.jobs import (
    jobs, jobs_lock, MAX_OUTPUT_LINES, MAX_RUNNING_JOBS, ACTIVE_JOB_STATES,
    EVIDENCE_SERVICE, EVIDENCE_ANALYTICS,
    build_command, run_job, cleanup_old_jobs, list_run_history,
    resolve_history_file, terminate_process_group, mark_cancellation_failure,
    force_evidence_state_terminal, initialize_evidence_dashboard_state,
    request_job_cancellation,
    read_evidence_job_state,
)

logger = logging.getLogger("genein_dashboard")
logger.setLevel(logging.INFO)


def ensure_dashboard_logging():
    """Open the panel log in the work directory. Importing this module does not create it."""
    from dashboard.config import LOG_DIR as configured_log_dir
    configured_log_dir.mkdir(parents=True, exist_ok=True)
    if logger.handlers:
        return
    file_handler = RotatingFileHandler(
        configured_log_dir / "ux_dashboard.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    logger.addHandler(file_handler)

CACHE_BYPASS_CONTENT_TYPES = {"text/html", "application/javascript", "text/css"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024


def validate_fastq_name(name):
    return any(str(name).lower().endswith(ext) for ext in (".fastq", ".fastq.gz", ".fq", ".fq.gz"))


def sanitize_token(text):
    if text is None:
        return None
    return str(text).replace("\r", "").replace("\n", "").strip()


def sanitize_for_log(value):
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("\0", " ")
    return text[:200]


def params_for_log(params):
    if not isinstance(params, dict):
        return sanitize_for_log(params)
    redacted = {}
    for key, value in params.items():
        if "token" in key.lower() or "password" in key.lower() or "secret" in key.lower():
            redacted[key] = "[redacted]"
        else:
            redacted[key] = sanitize_for_log(value)
    return redacted


def command_for_log(cmd):
    if isinstance(cmd, (list, tuple)):
        return " ".join(sanitize_for_log(arg) for arg in cmd)
    return sanitize_for_log(cmd)


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    handler.end_headers()
    handler.wfile.write(body)


def request_content_length(handler):
    raw = handler.headers.get("Content-Length", "0")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Content-Length invalido") from exc
    if value < 0:
        raise ValueError("Content-Length invalido")
    return value


def text_response(handler, status, text, content_type="text/plain; charset=utf-8"):
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve_file(handler, filepath, content_type, download=False):
    if not filepath.exists():
        logger.warning("Arquivo estático não encontrado: %s", filepath)
        handler.send_error(HTTPStatus.NOT_FOUND, "Arquivo não encontrado")
        return
    try:
        body = filepath.read_bytes()
    except OSError as exc:
        logger.error("Erro ao ler arquivo estático %s: %s", filepath, exc)
        handler.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Erro ao ler arquivo")
        return
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    if download:
        handler.send_header("Content-Disposition", f'attachment; filename="{filepath.name}"')
    if content_type.split(";")[0].strip() in CACHE_BYPASS_CONTENT_TYPES:
        handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Expires", "0")
    handler.end_headers()
    handler.wfile.write(body)


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def list_samples():
    raw_dir = REPO_ROOT / "data" / "raw"
    samples = set()
    if raw_dir.exists():
        for item in raw_dir.glob("*_R1.fastq.gz"):
            sample_id = item.name[:-12]
            r2_path = raw_dir / f"{sample_id}_R2.fastq.gz"
            if r2_path.exists():
                samples.add(sample_id)
        for item in raw_dir.glob("*_R1.fastq"):
            sample_id = item.name[:-9]
            r2_path = raw_dir / f"{sample_id}_R2.fastq"
            if r2_path.exists():
                samples.add(sample_id)
    return sorted(list(samples))


def cleanup_temp_files():
    errors = []
    freed = 0
    tmp_upload_dir = LOG_DIR / "uploads_tmp"
    if tmp_upload_dir.exists():
        for item in tmp_upload_dir.iterdir():
            try:
                if item.is_file():
                    freed += item.stat().st_size
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as exc:
                errors.append(f"Erro ao remover {item.name}: {exc}")
    return {"freed_bytes": freed, "errors": errors, "success": len(errors) == 0}


def import_uploaded_files(sample, r1_name, r1_data, r2_name, r2_data, replace=False):
    sample = require_sample_id(sample)
    if not validate_fastq_name(r1_name) or not validate_fastq_name(r2_name):
        raise ValueError("Extensao invalida (use .fastq ou .fastq.gz)")
    if not r1_data or not r2_data:
        raise ValueError("R1 e R2 nao podem ser vazios")
    if len(r1_data) > MAX_UPLOAD_BYTES or len(r2_data) > MAX_UPLOAD_BYTES:
        raise ValueError("FASTQ excede o limite de upload")

    raw_dir = REPO_ROOT / "data" / "raw"
    incoming_dir = REPO_ROOT / "data" / "incoming"
    raw_dir.mkdir(parents=True, exist_ok=True)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    out_r1 = raw_dir / f"{sample}_R1.fastq.gz"
    out_r2 = raw_dir / f"{sample}_R2.fastq.gz"
    if not replace and (out_r1.exists() or out_r2.exists()):
        raise FileExistsError(f"Amostra '{sample}' já existe; confirme substituição explicitamente")

    import gzip

    with tempfile.TemporaryDirectory(dir=incoming_dir, prefix=f".{sample}.upload-") as temp_name:
        temp_dir = Path(temp_name)
        tmp_r1 = temp_dir / "R1.fastq.gz"
        tmp_r2 = temp_dir / "R2.fastq.gz"
        if r1_name.lower().endswith(".gz"):
            tmp_r1.write_bytes(r1_data)
        else:
            with gzip.open(tmp_r1, "wb") as handle:
                handle.write(r1_data)
        if r2_name.lower().endswith(".gz"):
            tmp_r2.write_bytes(r2_data)
        else:
            with gzip.open(tmp_r2, "wb") as handle:
                handle.write(r2_data)
        count = validate_fastq(tmp_r1, tmp_r2)
        metadata = {
            "sample_id": sample,
            "read_count_pairs": count,
            "r1_name": Path(r1_name).name,
            "r2_name": Path(r2_name).name,
            "r1_size_bytes": len(r1_data), "r2_size_bytes": len(r2_data),
            "r1_sha256": _sha256_bytes(r1_data),
            "r2_sha256": _sha256_bytes(r2_data),
            "imported_at": datetime.now().astimezone().isoformat(),
            "source_scope": "operational_only",
        }
        metadata_path = incoming_dir / f"{sample}.json"
        backups = []
        promoted = []
        try:
            for target in (out_r1, out_r2):
                if target.exists():
                    backup = temp_dir / f"backup-{target.name}"
                    os.replace(target, backup)
                    backups.append((backup, target))
            for source, target in ((tmp_r1, out_r1), (tmp_r2, out_r2)):
                os.replace(source, target)
                promoted.append(target)
            atomic_json(metadata_path, metadata)
            for backup, _ in backups:
                backup.unlink(missing_ok=True)
        except Exception:
            for target in promoted:
                target.unlink(missing_ok=True)
            for backup, target in reversed(backups):
                if backup.exists():
                    os.replace(backup, target)
            raise


def import_zip_sample(sample, zip_bytes, replace=False):
    if not zip_bytes:
        raise ValueError("arquivo vazio")

    tmp_dir = LOG_DIR / "uploads_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    temp_zip = tmp_dir / f"tmp_upload_{uuid.uuid4().hex}.zip"
    temp_zip.write_bytes(zip_bytes)

    try:
        with zipfile.ZipFile(temp_zip) as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            expanded_size = sum(info.file_size for info in infos)
            if len(zip_bytes) > MAX_UPLOAD_BYTES:
                raise ValueError("arquivo ZIP excede o limite comprimido permitido")
            if expanded_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES or any(info.file_size > MAX_UPLOAD_BYTES for info in infos):
                raise ValueError("arquivo ZIP excede o limite descompactado permitido")
            if any(info.compress_size and info.file_size / info.compress_size > 1000 for info in infos):
                raise ValueError("arquivo ZIP possui razao de compressao incompatível com upload seguro")
            names = [info.filename for info in infos]
            fastqs = [n for n in names if validate_fastq_name(n.lower())]
            r1_candidates = [n for n in fastqs if "r1" in n.lower()]
            r2_candidates = [n for n in fastqs if "r2" in n.lower()]
            if len(r1_candidates) != 1:
                raise ValueError("R1 não encontrado no .zip")
            if len(r2_candidates) != 1:
                raise ValueError("R2 não encontrado no .zip")

            r1_name = r1_candidates[0]
            r2_name = r2_candidates[0]
            import_uploaded_files(sample, Path(r1_name).name, zf.read(r1_name), Path(r2_name).name, zf.read(r2_name), replace=replace)
    finally:
        temp_zip.unlink(missing_ok=True)


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self._do_GET_inner()
        except FileNotFoundError as exc:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except Exception as exc:
            logger.error("Exceção não tratada em do_GET path=%s: %s\n%s", getattr(self, "path", "?"), exc, traceback.format_exc())
            try:
                json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Erro interno do servidor"})
            except Exception:
                pass

    def _do_GET_inner(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/help":
            documents = {"guia": "docs/uso-e-bancos.md", "bancos": "docs/uso-e-bancos.md", "hospedeiro": "docs/HOSPEDEIRO_BETA.md", "licenca": "LICENSE", "terceiros": "THIRD_PARTY_NOTICES.md"}
            key = query_one(query, "doc") or "guia"
            if key not in documents:
                return self.send_error(HTTPStatus.NOT_FOUND, "Documento não disponível")
            content = html.escape((REPO_ROOT / documents[key]).read_text(encoding="utf-8"))
            links = " | ".join(f'<a href="/help?doc={name}">{name}</a>' for name in documents)
            page = f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Ajuda Gene-In</title><body><h1>Ajuda Gene-In</h1><nav><a href="/">Voltar ao painel</a> | {links}</nav><pre style="white-space:pre-wrap;font:16px/1.6 sans-serif;max-width:1000px">{content}</pre></body></html>'
            return text_response(self, HTTPStatus.OK, page, "text/html; charset=utf-8")
        if parsed.path in {"/", "/index.html"}:
            return serve_file(self, DASHBOARD_DIR / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/api/dbs":
            return json_response(self, HTTPStatus.OK, {"dbs": list_db_profiles()})
        if parsed.path in {"/styles.css", "/tokens.css", "/gene-in.css"}:
            return serve_file(self, DASHBOARD_DIR / parsed.path.lstrip("/"), "text/css; charset=utf-8")
        if parsed.path.startswith("/vendor/fonts/"):
            font_name = parsed.path.removeprefix("/vendor/fonts/")
            if "/" in font_name or "\\" in font_name or not font_name.endswith(".woff2"):
                return self.send_error(HTTPStatus.NOT_FOUND, "Fonte não encontrada")
            font_dir = (DASHBOARD_DIR / "vendor" / "fonts").resolve()
            font = (font_dir / font_name).resolve()
            if font.parent != font_dir or not font.is_file():
                return self.send_error(HTTPStatus.NOT_FOUND, "Fonte não encontrada")
            return serve_file(self, font, "font/woff2")
        if parsed.path.startswith("/js/"):
            module_name = parsed.path.removeprefix("/js/")
            if module_name in JAVASCRIPT_MODULES:
                return serve_file(
                    self,
                    DASHBOARD_DIR / "js" / module_name,
                    "application/javascript; charset=utf-8",
                )
            return self.send_error(HTTPStatus.NOT_FOUND, "Módulo não encontrado")
        if parsed.path == "/vendor/d3-7.9.0.min.js":
            return serve_file(
                self, DASHBOARD_DIR / "vendor" / "d3-7.9.0.min.js",
                "application/javascript; charset=utf-8",
            )
        if parsed.path == "/vendor/observable-plot-0.6.17.min.js":
            return serve_file(
                self, DASHBOARD_DIR / "vendor" / "observable-plot-0.6.17.min.js",
                "application/javascript; charset=utf-8",
            )
        if parsed.path == "/hero-bg.png":
            return serve_file(self, DASHBOARD_DIR / "hero-bg.png", "image/png")
        if parsed.path == "/gene-in-logo.png":
            return serve_file(self, DASHBOARD_DIR / "gene-in-logo.png", "image/png")
        if parsed.path in {"/favicon.ico", "/gene-in-symbol.png"}:
            return serve_file(self, DASHBOARD_DIR / "gene-in-symbol.png", "image/png")
        if parsed.path == "/api/samples":
            return json_response(self, HTTPStatus.OK, {"samples": list_samples()})
        if parsed.path == "/api/targets":
            return json_response(self, HTTPStatus.OK, {"targets": list_targets()})
        if parsed.path == "/api/preflight":
            return json_response(self, HTTPStatus.OK, get_preflight_status())
        if parsed.path == "/api/history":
            return json_response(self, HTTPStatus.OK, {"runs": list_run_history()})
        if parsed.path == "/api/experimental/contig-sources":
            return json_response(self, HTTPStatus.OK, {"sources": list_sources(REPO_ROOT)})
        if parsed.path == "/api/experimental/contig-comparisons":
            return json_response(self, HTTPStatus.OK, {"comparisons": list_comparisons(REPO_ROOT)})
        if parsed.path == "/api/experimental/contig-comparison/artifact":
            target = comparison_artifact(
                REPO_ROOT,
                query_one(query, "comparison"),
                query_one(query, "type"),
            )
            ctype = (
                "application/json; charset=utf-8" if target.suffix == ".json"
                else "text/tab-separated-values; charset=utf-8" if target.suffix == ".tsv"
                else "text/plain; charset=utf-8"
            )
            return serve_file(self, target, ctype)
        if parsed.path == "/api/evidence/config":
            return json_response(self, HTTPStatus.OK, EVIDENCE_SERVICE.config())
        if parsed.path == "/api/evidence/dependencies":
            dependencies = EVIDENCE_SERVICE.dependencies()
            return json_response(self, HTTPStatus.OK if dependencies.get("valid") else HTTPStatus.SERVICE_UNAVAILABLE, dependencies)
        if parsed.path == "/api/evidence/manifests":
            return json_response(self, HTTPStatus.OK, {"manifests": EVIDENCE_SERVICE.list_manifests()})
        if parsed.path == "/api/evidence/manifest":
            return json_response(self, HTTPStatus.OK, EVIDENCE_SERVICE.manifest(query_one(query, "id")))
        if parsed.path == "/api/evidence/manifest/export":
            target = EVIDENCE_SERVICE.manifest_export(query_one(query, "id"))
            return serve_file(self, target, "text/tab-separated-values; charset=utf-8")
        if parsed.path == "/api/evidence/run":
            return json_response(self, HTTPStatus.OK, EVIDENCE_SERVICE.state(query_one(query, "id")))
        if parsed.path == "/api/evidence/result":
            if query_one(query, "refresh") == "1":
                EVIDENCE_SERVICE.refresh_inspection(query_one(query, "run"))
            return json_response(self, HTTPStatus.OK, EVIDENCE_SERVICE.result(query_one(query, "run")))
        if parsed.path == "/api/evidence/analytics":
            return json_response(
                self, HTTPStatus.OK,
                EVIDENCE_ANALYTICS.summary(query_one(query, "run")),
            )
        if parsed.path == "/api/evidence/analytics/dataset":
            return json_response(
                self, HTTPStatus.OK,
                EVIDENCE_ANALYTICS.dataset(
                    query_one(query, "run"),
                    query_one(query, "dataset"),
                    reference_id=query_one(query, "reference_id"),
                    locus_id=query_one(query, "locus_id"),
                    offset=query_one(query, "offset") or 0,
                    limit=query_one(query, "limit") or 100,
                ),
            )
        if parsed.path == "/api/evidence/analytics/compare":
            return json_response(
                self, HTTPStatus.OK,
                EVIDENCE_ANALYTICS.compare(query.get("run") or []),
            )
        if parsed.path == "/api/evidence/artifact":
            target = EVIDENCE_SERVICE.artifact(
                query_one(query, "run"), query_one(query, "type")
            )
            if target.suffix == ".json":
                ctype = "application/json; charset=utf-8"
            elif target.suffix in {".bam", ".bai"}:
                ctype = "application/octet-stream"
            else:
                ctype = "text/plain; charset=utf-8"
            return serve_file(self, target, ctype, download=query_one(query, "type") in {
                "candidate_fasta", "candidate_sequences", "candidate_queries",
            })
        # P&D experimental (mapeamento direto): descoberta somente-leitura,
        # separada do fluxo canonico Evidence V2 / Alpha.2.
        if parsed.path == "/api/experimental/direct-map/runs":
            return json_response(self, HTTPStatus.OK, list_direct_map_runs())
        if parsed.path == "/api/experimental/direct-map/run":
            return json_response(
                self, HTTPStatus.OK, direct_map_run(query_one(query, "run"))
            )
        if parsed.path == "/api/experimental/direct-map/artifact":
            target = direct_map_artifact(
                query_one(query, "run"), query_one(query, "type")
            )
            ctype = (
                "application/json; charset=utf-8" if target.suffix == ".json"
                else "text/tab-separated-values; charset=utf-8" if target.suffix == ".tsv"
                else "text/plain; charset=utf-8"
            )
            return serve_file(self, target, ctype)
        if parsed.path == "/api/config/env":
            try:
                config = load_config_env()
                return json_response(self, HTTPStatus.OK, {"config": config})
            except ValueError as exc:
                return json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc), "success": False})
            except Exception as exc:
                logger.error("Erro ao carregar configuração: %s\n%s", exc, traceback.format_exc())
                return json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Não foi possível carregar a configuração."})
        if parsed.path == "/api/config/environment":
            try:
                status = get_environment_status()
                return json_response(self, HTTPStatus.OK, status)
            except Exception as exc:
                logger.error("Erro ao obter status do ambiente: %s\n%s", exc, traceback.format_exc())
                return json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Não foi possível obter o status do ambiente."})
        if parsed.path == "/api/history/file":
            query = parse_qs(parsed.query)
            target = resolve_history_file(query_one(query, "run"), query_one(query, "type"))
            if not target:
                logger.warning("Arquivo de histórico não encontrado: run=%s type=%s", query_one(query, "run"), query_one(query, "type"))
                return self.send_error(HTTPStatus.NOT_FOUND, "Arquivo do histórico não encontrado")
            ctype = "text/markdown; charset=utf-8" if target.suffix == ".md" else "text/plain; charset=utf-8"
            return serve_file(self, target, ctype)
        if parsed.path.startswith("/api/job/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            cleanup_old_jobs()
            with jobs_lock:
                job = jobs.get(job_id)
            if not job:
                logger.warning("Job não encontrado: %s", job_id)
                return json_response(self, HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            state = read_evidence_job_state(job_id) if job.get("action") in {"evidence_pipeline", "evidence_batch"} else {}
            return json_response(self, HTTPStatus.OK, {
                "id": job_id, "status": job.get("status"), "action": job.get("action"),
                "started_at": job.get("started_at"), "finished_at": job.get("finished_at"),
                "output": "\n".join(job.get("output", [])),
                "returncode": job.get("returncode"),
                "command": job.get("command"),
                "log_path": job.get("log_path"),
                "run": job.get("run"),
                "tail": job.get("tail", ""),
                "official_v1_status": job.get("official_v1_status"),
                "evidence_v2_status": job.get("evidence_v2_status"),
                "experimental_warning": job.get("experimental_warning"),
                "experimental_analysis_outcome": job.get("experimental_analysis_outcome"),
                "stage_status": state.get("stages") or ([{"id": "contig_comparison", "label": "Comparação de contigs", "status": job["stage_status"]}] if isinstance(job.get("stage_status"), str) else job.get("stage_status")),
                "failed_stage": state.get("failed_stage"),
                "failure_type": state.get("failure_type") or job.get("failure_type"),
                "failure_message": state.get("failure_message") or job.get("failure_message"),
            })
        logger.warning("Rota GET não encontrada: %s", self.path)
        return self.send_error(HTTPStatus.NOT_FOUND, "Rota inválida")

    def do_POST(self):
        try:
            self._do_POST_inner()
        except FileExistsError as exc:
            json_response(self, HTTPStatus.CONFLICT, {"error": str(exc)})
        except FileNotFoundError as exc:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except Exception as exc:
            logger.error("Exceção não tratada em do_POST path=%s: %s\n%s", getattr(self, "path", "?"), exc, traceback.format_exc())
            try:
                json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Erro interno do servidor"})
            except Exception:
                pass

    def _do_POST_inner(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/import-upload":
            return self.handle_upload_import()
        if parsed.path == "/api/experimental/contig-sources/import":
            return self.handle_contig_fasta_import()

        try:
            content_length = request_content_length(self)
        except ValueError as exc:
            return text_response(self, HTTPStatus.BAD_REQUEST, str(exc))
        if content_length > MAX_UPLOAD_BYTES:
            logger.warning("Upload recusado por tamanho em POST: %s bytes (limite %s bytes)", content_length, MAX_UPLOAD_BYTES)
            return text_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload muito grande. Limite atual: 500 MB. Use arquivos menores ou importe os FASTQs manualmente para data/raw/.")
        if content_length <= 0:
            return text_response(self, HTTPStatus.BAD_REQUEST, "Body vazio")
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning("JSON inválido recebido em POST %s", parsed.path)
            return text_response(self, HTTPStatus.BAD_REQUEST, "JSON inválido")

        if parsed.path == "/api/evidence/config/validate":
            return json_response(self, HTTPStatus.OK, EVIDENCE_SERVICE.validate_config_text(payload.get("content", "")))
        if parsed.path == "/api/evidence/manifests/validate":
            result = EVIDENCE_SERVICE.validate_manifest(payload.get("rows"), validate_files=True)
            return json_response(self, HTTPStatus.OK if result["valid"] else HTTPStatus.BAD_REQUEST, result)
        if parsed.path == "/api/evidence/manifests/save":
            result = EVIDENCE_SERVICE.save_manifest(payload.get("rows"), payload.get("manifest_id"))
            return json_response(self, HTTPStatus.OK if result["valid"] else HTTPStatus.BAD_REQUEST, result)
        if parsed.path == "/api/evidence/manifests/import":
            return json_response(self, HTTPStatus.OK, EVIDENCE_SERVICE.import_manifest(payload.get("content", "")))
        if parsed.path == "/api/evidence/run":
            mode = str(payload.get("mode") or "individual").lower()
            params = payload.get("params") or {}
            if mode == "individual":
                return self.start_job("evidence_pipeline", params)
            if mode == "batch":
                return self.start_job("evidence_batch", params)
            return json_response(self, HTTPStatus.BAD_REQUEST, {"error": "mode deve ser individual ou batch"})

        if parsed.path == "/api/host-index/validate":
            result = validate_host_index(payload.get("prefix", ""))
            status = HTTPStatus.OK if result["valid"] else HTTPStatus.BAD_REQUEST
            return json_response(self, status, result)

        if parsed.path == "/api/config/env":
            prevalidated_updates = payload.get("config", {})
            try:
                validate_config_updates(prevalidated_updates)
            except ValueError as exc:
                return json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc), "success": False})
            try:
                updates = payload.get("config", {})
                if not isinstance(updates, dict):
                    return json_response(self, HTTPStatus.BAD_REQUEST, {"error": "config deve ser um objeto JSON", "success": False})
                for key in updates:
                    if key not in SUPPORTED_ENV_KEYS:
                        logger.warning("Chave de configuração não suportada: %s", key)
                        return json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"Chave não suportada: {key}", "success": False})

                save_config_env(updates)
                logger.info("Configuração salva: %s", list(updates.keys()))
                return json_response(self, HTTPStatus.OK, {"success": True, "message": "Configuração atualizada com sucesso"})
            except Exception as exc:
                logger.error("Erro ao salvar configuração: %s\n%s", exc, traceback.format_exc())
                return json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Não foi possível salvar a configuração.", "success": False})

        if parsed.path == "/api/config/environment/rebuild":
            if not INSTALL_WSL_SCRIPT.exists():
                logger.error("Script não encontrado: %s", INSTALL_WSL_SCRIPT)
                return json_response(self, HTTPStatus.NOT_FOUND, {"error": "Script bundle/install_wsl.sh não encontrado", "success": False})

            return self.start_job("rebuild_env", {})

        if parsed.path == "/api/history/rerun":
            raw_run_dir = payload.get("run_dir")
            if not isinstance(raw_run_dir, str):
                logger.warning("rerun: run_dir inválido (tipo): %r", type(raw_run_dir))
                return text_response(self, HTTPStatus.BAD_REQUEST, "run_dir inválido")
            run_dir = raw_run_dir.strip()
            if not run_dir:
                logger.warning("rerun: run_dir vazio")
                return text_response(self, HTTPStatus.BAD_REQUEST, "run_dir obrigatório")
            runs_dir = RUNS_DIR
            run_json = runs_dir / run_dir / "run.json"
            try:
                run_json.resolve().relative_to(runs_dir.resolve())
            except ValueError:
                return text_response(self, HTTPStatus.BAD_REQUEST, "run_dir invalido")
            if not run_json.exists():
                logger.warning("rerun: run.json não encontrado para run_dir='%s'", run_dir)
                return text_response(self, HTTPStatus.NOT_FOUND, "run.json não encontrado")
            try:
                data = json.loads(run_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("rerun: erro ao ler run.json '%s': %s", run_json, exc)
                return text_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, "Não foi possível reler a execução.")
            logger.info("rerun: relançando run_dir='%s' action='%s'", run_dir, data.get("action"))
            return self.start_job(data.get("action", "pipeline"), data.get("params") or {})

        if parsed.path == "/api/cleanup":
            try:
                result = cleanup_temp_files()
                if result.get("errors"):
                    logger.warning("[cleanup] Erros durante limpeza: %s", result["errors"])
                return json_response(self, HTTPStatus.OK, result)
            except Exception as exc:
                logger.error("Erro durante limpeza: %s\n%s", exc, traceback.format_exc())
                return json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Erro durante limpeza: {exc}", "success": False})

        if parsed.path.startswith("/api/job/") and parsed.path.endswith("/cancel"):
            parts = parsed.path.split("/")
            job_id = parts[3] if len(parts) >= 5 else ""
            cancellation = request_job_cancellation(job_id)
            if not cancellation["found"]:
                return json_response(self, HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            if not cancellation["ok"]:
                return json_response(self, HTTPStatus.OK, {
                    "ok": False,
                    "message": f"Job não está em execução (status={cancellation['status']})",
                })
            process = cancellation["process"]
            if process is None and cancellation["status"] == "cancelled":
                if cancellation["action"] == "compare_contigs":
                    finalize_contig_comparison_cancellation(
                        REPO_ROOT, job_id,
                        "Execucao cancelada antes do lancamento do processo",
                    )
                if cancellation["action"] in {"evidence_pipeline", "evidence_batch"}:
                    force_evidence_state_terminal(
                        job_id, "cancelled",
                        "Execução cancelada antes do lançamento do processo.",
                    )
            if process is not None:
                import signal as _signal
                signal_value = _signal.SIGTERM if os.name != "nt" else getattr(_signal, "CTRL_BREAK_EVENT", _signal.SIGTERM)
                terminated, error = terminate_process_group(process, signal_value)
                if terminated:
                    logger.info("[job:%s] SIGTERM enviado para cancelamento.", job_id)
                else:
                    logger.error("[job:%s] Falha ao cancelar grupo de processos: %s", job_id, error)
                    mark_cancellation_failure(job_id, cancellation["action"], "Falha ao encerrar o grupo de processos; revisão manual é necessária.")
                    return json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Falha ao encerrar grupo de processos", "failure_type": "CANCELLATION_FAILED"})
                
                def _force_kill(p, jid):
                    import time as _time
                    import signal as _signal
                    _time.sleep(3)
                    if p.poll() is not None:
                        return
                    force_signal = getattr(_signal, "SIGKILL", _signal.SIGTERM)
                    killed, kill_error = terminate_process_group(p, force_signal)
                    if killed:
                        logger.info("[job:%s] SIGKILL enviado (processo não encerrou com SIGTERM).", jid)
                        return
                    logger.error("[job:%s] Falha ao encerrar grupo de processos: %s", jid, kill_error)
                    mark_cancellation_failure(jid, jobs.get(jid, {}).get("action"), "Falha ao encerrar o grupo de processos; revisão manual é necessária.")
                import threading
                threading.Thread(target=_force_kill, args=(process, job_id), daemon=True).start()
            logger.info("[job:%s] Cancelamento solicitado pelo usuário.", job_id)
            return json_response(self, HTTPStatus.OK, {"ok": True, "message": "Cancelamento solicitado"})

        if parsed.path != "/api/run":
            logger.warning("Rota POST não encontrada: %s", parsed.path)
            return self.send_error(HTTPStatus.NOT_FOUND, "Rota inválida")
        return self.start_job(payload.get("action"), payload.get("params") or {})

    def handle_upload_import(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return text_response(self, HTTPStatus.BAD_REQUEST, "Content-Type deve ser multipart/form-data")

        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip('"')
                break
        if not boundary:
            return text_response(self, HTTPStatus.BAD_REQUEST, "Boundary ausente no Content-Type")

        try:
            content_length = request_content_length(self)
        except ValueError as exc:
            return text_response(self, HTTPStatus.BAD_REQUEST, str(exc))
        if content_length > MAX_UPLOAD_BYTES:
            logger.warning("Upload recusado por tamanho em handle_upload_import: %s bytes (limite %s bytes)", content_length, MAX_UPLOAD_BYTES)
            return text_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload muito grande. Limite atual: 500 MB. Use arquivos menores ou importe os FASTQs manualmente para data/raw/.")
        if content_length <= 0:
            return text_response(self, HTTPStatus.BAD_REQUEST, "Body vazio")
        raw_body = self.rfile.read(content_length)

        msg_text = f"Content-Type: {content_type}\r\n\r\n".encode() + raw_body
        msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(msg_text)

        fields = {}
        for part in msg.get_payload():
            if not hasattr(part, 'get_payload'):
                continue
            cd = part.get("Content-Disposition", "")
            name = None
            filename = None
            for item in cd.split(";"):
                item = item.strip()
                if item.startswith('name="'):
                    name = item[6:-1]
                elif item.startswith('filename="'):
                    filename = item[10:-1]
            if name:
                payload = part.get_payload(decode=True)
                fields[name] = {"data": payload, "filename": filename}

        sample = (fields.get("sample", {}).get("data") or b"").decode("utf-8", errors="replace").strip()
        if not sample:
            return text_response(self, HTTPStatus.BAD_REQUEST, "Campo obrigatório: sample")

        try:
            zip_field = fields.get("zipfile")
            r1_field = fields.get("r1file")
            r2_field = fields.get("r2file")
            replace = (fields.get("replace", {}).get("data") or b"").decode().lower() == "true"
            if replace and any(item.get("sample") == sample and item.get("status") in ACTIVE_JOB_STATES for item in jobs.values()):
                raise ValueError("Amostra em processamento; aguarde antes de substituir as entradas.")

            if zip_field and zip_field.get("filename") and zip_field.get("data"):
                import_zip_sample(sample, zip_field["data"], replace=replace)
            elif (r1_field and r1_field.get("filename") and r1_field.get("data")
                  and r2_field and r2_field.get("filename") and r2_field.get("data")):
                import_uploaded_files(
                    sample,
                    r1_field["filename"], r1_field["data"],
                    r2_field["filename"], r2_field["data"], replace=replace
                )
            else:
                return text_response(self, HTTPStatus.BAD_REQUEST, "Envie R1/R2 ou arquivo .zip")
        except FileExistsError as exc:
            logger.warning("Amostra duplicada no upload '%s': %s", sample, exc)
            return text_response(self, HTTPStatus.CONFLICT, str(exc))
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            logger.warning("Erro no upload de amostra '%s': %s", sample, exc)
            return text_response(self, HTTPStatus.BAD_REQUEST, str(exc))
        logger.info("Upload importado com sucesso: sample='%s'", sample)
        metadata = json.loads((REPO_ROOT / "data/incoming" / f"{sample}.json").read_text())
        return json_response(self, HTTPStatus.OK, {
            "message": f"Amostra importada: {sample}",
            "sample_id": sample,
            "r1": f"data/raw/{sample}_R1.fastq.gz",
            "r2": f"data/raw/{sample}_R2.fastq.gz",
            "source_scope": "operational_only",
            "metadata": metadata,
        })

    def handle_contig_fasta_import(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return text_response(self, HTTPStatus.BAD_REQUEST, "Content-Type deve ser multipart/form-data")
        content_length = request_content_length(self)
        if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
            return text_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "FASTA local vazio ou acima do limite de 500 MB")
        raw_body = self.rfile.read(content_length)
        message = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(
            f"Content-Type: {content_type}\r\n\r\n".encode() + raw_body
        )
        fields = {}
        for part in message.get_payload():
            disposition = part.get("Content-Disposition", "")
            field_name = None
            filename = None
            for token in disposition.split(";"):
                token = token.strip()
                if token.startswith('name="'):
                    field_name = token[6:-1]
                elif token.startswith('filename="'):
                    filename = token[10:-1]
            if field_name:
                fields[field_name] = {
                    "data": part.get_payload(decode=True) or b"", "filename": filename,
                }
        sample = (fields.get("sample", {}).get("data") or b"").decode("utf-8", errors="strict").strip()
        origin = (fields.get("origin", {}).get("data") or b"").decode("utf-8", errors="strict").strip()
        fasta_field = fields.get("fasta") or {}
        fasta_bytes = fasta_field.get("data") or b""
        if not sample or not origin or not fasta_bytes:
            return text_response(self, HTTPStatus.BAD_REQUEST, "sample, origin e fasta sao obrigatorios")
        source_id = uuid.uuid4().hex
        incoming = REPO_ROOT / "results" / "contig_sources" / ".incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        temporary = incoming / f"{source_id}.fasta"
        try:
            temporary.write_bytes(fasta_bytes)
            result = import_local_fasta(REPO_ROOT, temporary, sample, origin, source_id)
        finally:
            temporary.unlink(missing_ok=True)
        return json_response(self, HTTPStatus.OK, result)

    def start_job(self, action, params):
        cleanup_old_jobs()
        if action not in {"check_env", "demo", "import_sample", "build_db", "pipeline", "rebuild_env", "advanced_analysis", "assembly_only", "compare_contigs", "evidence_pipeline", "evidence_batch"}:
            logger.warning("Tentativa de ação inválida: '%s'", action)
            return text_response(self, HTTPStatus.BAD_REQUEST, "Ação inválida")
        params = params or {}
        if not isinstance(params, dict):
            return text_response(self, HTTPStatus.BAD_REQUEST, "params deve ser um objeto JSON")
        sample = None
        if action in {"import_sample", "pipeline", "advanced_analysis", "assembly_only", "compare_contigs", "evidence_pipeline"}:
            try:
                sample = require_sample_id(params.get("sample"))
            except ValueError as exc:
                return text_response(self, HTTPStatus.BAD_REQUEST, str(exc))
            params = dict(params)
            params["sample"] = sample

        job_id = uuid.uuid4().hex
        params = dict(params)
        if action in {"pipeline", "evidence_pipeline", "evidence_batch"}:
            _, proposed_env = build_command(action, params)
            if proposed_env.get("HOST_FILTER_ENABLED") == "true":
                checked = validate_host_index(proposed_env.get("HOST_INDEX_PREFIX"))
                if not checked["valid"]:
                    return json_response(self, HTTPStatus.BAD_REQUEST, {"error": checked["reason"]})
        if action == "compare_contigs":
            params["comparison_id"] = job_id
            build_command(action, params)
        if action in {"evidence_pipeline", "evidence_batch"}:
            params["run_id"] = job_id
            build_command(action, params)
            config_value = str(params.get("config") or "config/evidence_profiles.json")
            config_path = Path(config_value)
            config_path = config_path if config_path.is_absolute() else REPO_ROOT / config_path
            config_path = config_path.resolve()
            try:
                config_path.relative_to(REPO_ROOT.resolve())
            except ValueError as exc:
                raise ValueError("config Evidence V2 deve estar dentro do projeto") from exc
            if not config_path.is_file():
                raise ValueError("configuração Evidence V2 não encontrada")
            EVIDENCE_SERVICE.validate_config_text(config_path.read_text(encoding="utf-8"))
        with jobs_lock:
            running = sum(1 for item in jobs.values() if item.get("status") in ACTIVE_JOB_STATES)
            if running >= MAX_RUNNING_JOBS:
                return json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"error": "Limite de jobs simultaneos atingido"})
            if sample and any(
                item.get("sample") == sample and item.get("status") in ACTIVE_JOB_STATES
                for item in jobs.values()
            ):
                return json_response(self, HTTPStatus.CONFLICT, {"error": f"A amostra '{sample}' ja possui um job em execucao"})
            if action in {"build_db", "rebuild_env", "compare_contigs"} and any(
                item.get("action") in {"build_db", "rebuild_env"}
                and item.get("status") in ACTIVE_JOB_STATES
                for item in jobs.values()
            ):
                return json_response(self, HTTPStatus.CONFLICT, {"error": "Ja existe uma operacao de ambiente/banco em execucao"})
            if action in {"build_db", "rebuild_env"} and any(
                item.get("action") == "compare_contigs" and item.get("status") in ACTIVE_JOB_STATES
                for item in jobs.values()
            ):
                return json_response(self, HTTPStatus.CONFLICT, {"error": "Ja existe uma comparacao consumindo um banco"})
            if action == "evidence_batch" and any(
                item.get("action") == "evidence_batch"
                and item.get("manifest_id") == params.get("manifest_id")
                and item.get("status") in ACTIVE_JOB_STATES
                for item in jobs.values()
            ):
                return json_response(self, HTTPStatus.CONFLICT, {"error": "Este manifesto ja possui uma execucao Evidence V2 em andamento"})
            jobs[job_id] = {
                "status": "queued", "created_at": datetime.now().astimezone().isoformat(), "action": action,
                "sample": sample, "manifest_id": params.get("manifest_id"),
                "output": [], "returncode": None,
            }
        if action in {"evidence_pipeline", "evidence_batch"}:
            try:
                initialize_evidence_dashboard_state(action, params)
            except Exception:
                with jobs_lock:
                    jobs.pop(job_id, None)
                raise
        logger.info("Job enfileirado: id=%s action='%s' params=%s", job_id, action, params_for_log(params))
        import threading
        threading.Thread(target=run_job, args=(job_id, action, params), daemon=True).start()
        return json_response(self, HTTPStatus.OK, {"job_id": job_id})

    def log_message(self, format, *args):
        msg = format % args
        parts = msg.split('"')
        status_code = None
        if len(parts) >= 3:
            after_quote = parts[2].strip().split()
            if after_quote and after_quote[0].isdigit():
                status_code = int(after_quote[0])
        if status_code is not None and status_code >= 500:
            logger.error("HTTP %s %s", self.address_string(), msg)
        elif status_code is not None and status_code >= 400:
            logger.warning("HTTP %s %s", self.address_string(), msg)
        else:
            logger.debug("HTTP %s %s", self.address_string(), msg)

    def send_error(self, code, message=None, explain=None):
        logger.error("Erro HTTP %s: %s | path=%s | client=%s", code, message, getattr(self, "path", "?"), self.address_string())
        super().send_error(code, message, explain)
