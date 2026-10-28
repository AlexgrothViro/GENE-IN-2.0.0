"""
Gene-In Dashboard Jobs & Execution Management Module
Gerenciador de jobs em segundo plano, monitoramento de processos, cancelamento e histórico.
"""

import json
import logging
import os
import re
import secrets
import shlex
import shutil
import signal
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from subprocess import PIPE, STDOUT, Popen, run

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "experimental" / "contig_comparison"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from input_validation import FASTQ_SUFFIXES, validate_run_id, validate_sample_id
from evidence_dashboard import EvidenceDashboardService, atomic_json
from evidence_analytics import EvidenceAnalyticsService
from run_state import (
    RUN_STATUSES, TERMINAL_RUN_STATUSES, mutate_state_file, read_state,
    reserve_state as reserve_evidence_state,
)
from analysis_profiles import load_profiles, resolve_profile
from common import fsync_directory, sha256_file
from contig_comparison import (
    finalize_contig_comparison_cancellation, list_comparisons, resolve_source,
    safe_id, safe_name,
)
from dashboard.config import (
    LOG_DIR, RUNS_DIR, REPO_ROOT, iso_now, _DB_ALIAS, host_env_from_params,
    runtime_environment,
    load_config_env, validate_config_updates, save_config_env,
    get_repo_root, get_runs_dir, user_config_env_path,
)
from genein.paths import resolve_blast_db

EVIDENCE_SERVICE = EvidenceDashboardService(REPO_ROOT, background_inspection=True)
EVIDENCE_ANALYTICS = EvidenceAnalyticsService(EVIDENCE_SERVICE)

def get_evidence_service():
    if "ux_dashboard" in sys.modules and hasattr(sys.modules["ux_dashboard"], "EVIDENCE_SERVICE"):
        return sys.modules["ux_dashboard"].EVIDENCE_SERVICE
    return EVIDENCE_SERVICE

jobs = {}
jobs_lock = threading.Lock()

MAX_OUTPUT_LINES = 4000
JOB_TTL_SECONDS = 24 * 60 * 60
MAX_JOBS_IN_MEMORY = 100
MAX_RUNNING_JOBS = 4
ACTIVE_JOB_STATES = frozenset({"queued", "starting", "running", "cancelling"})
TERMINAL_JOB_STATES = frozenset({"done", "done_with_warning", "blocked", "failed", "cancelled"})


def initialize_evidence_dashboard_state(action, params):
    run_id = validate_run_id(params["run_id"])
    service = get_evidence_service()
    if action == "evidence_pipeline":
        samples = [params["sample"]]
        batch_id = validate_sample_id(params["batch_id"]) if params.get("batch_id") else None
        state_action = "evidence_single"
    else:
        manifest = service.manifest(params["manifest_id"])
        samples = [row["sample_id"] for row in manifest["rows"]]
        batch_id = manifest["metadata"].get("batch_id")
        state_action = "evidence_batch"
    state_path = service.evidence_root / "state" / f"{run_id}.json"
    reservation_token = secrets.token_urlsafe(32)
    reserve_evidence_state(
        state_path, run_id, state_action, samples, batch_id, reservation_token,
    )
    params["reservation_token"] = reservation_token


def force_evidence_state_terminal(run_id, status, message, failure_type=None, failed_command=None, failed_stage=None):
    """Close a dashboard-owned V2 state when failure happens before the V2 runner can do it."""
    if not run_id:
        return
    service = get_evidence_service()
    state_path = service.evidence_root / "state" / f"{run_id}.json"
    state = read_evidence_job_state(run_id)
    resource_failure = failure_type in {"MEMORY_EXHAUSTED", "PROCESS_KILLED", "PROCESS_TERMINATED"}
    if not state or (state["status"] in TERMINAL_RUN_STATUSES and not (state["status"] in {"failed", "cancelled"} and resource_failure)):
        return
    job_metadata = jobs.get(run_id, {})
    failure_type = failure_type or job_metadata.get("failure_type") or ("CANCELLED" if status == "cancelled" else "TOOL_FAILURE")
    failed_command = failed_command or job_metadata.get("command")

    def terminalize(state):
        if state.get("run_id") != run_id:
            raise ValueError("run state identity changed before terminalization")
        if state.get("status") in {"failed", "cancelled"} and resource_failure:
            state.update({"status": "failed", "evidence_v2_status": "failed", "failure_type": failure_type, "failure_message": message})
            for item in state.get("stages", []):
                if item.get("status") in {"failed", "cancelled"}:
                    item["status"] = "failed"
                    item["message"] = message
            return
        if state.get("status") in {"done", "done_with_warning", "blocked", "failed", "cancelled"}:
            return
        stage_status = "cancelled" if status == "cancelled" else "failed"
        stage = next((item for item in state.get("stages", []) if item.get("status") == "running"), None)
        stage = stage or next((item for item in state.get("stages", []) if item.get("status") == "pending"), None)
        if failed_stage == "database_preflight":
            # The database check sits after input validation and before QC.
            # Do not attribute that failure to the next pending stage.
            stage = None
        timestamp = datetime.now().astimezone().isoformat()
        previous_stage = state.get("current_stage")
        if stage:
            stage.update({
                "status": stage_status,
                "started_at": stage.get("started_at") or timestamp,
                "finished_at": timestamp,
                "message": message,
            })
        if state.get("official_v1_status") == "running" and state.get("evidence_v2_status") in {"queued", "not_started"}:
            state["official_v1_status"] = "cancelled" if status == "cancelled" else "failed"
        state.update({
            "status": status,
            "evidence_v2_status": status,
            "execution_status": status,
            "analysis_outcome": "NOT_EVALUABLE",
            "evidence_level": "NOT_EVALUABLE",
            "current_stage": None,
            "finished_at": timestamp,
            "failed_stage": failed_stage or (stage.get("id") if stage else previous_stage),
            "failure_type": failure_type,
            "failure_message": message,
            "failed_command": failed_command,
        })

    mutate_state_file(state_path, terminalize)


def terminate_process_group(process, signal_value) -> tuple[bool, str | None]:
    """Signal the complete job group and report failure instead of swallowing it."""
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal_value)
        elif getattr(signal, "SIGKILL", None) is not None and signal_value == signal.SIGKILL:
            process.kill()
        else:
            process.send_signal(signal_value)
    except (OSError, ProcessLookupError, ValueError) as exc:
        return False, f"could not signal process group: {exc}"
    return True, None


def claim_job_for_execution(job_id, command_text, log_path_text) -> bool:
    """Atomically reserve a queued job before creating its subprocess."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return False
        if job.get("status") in {"cancelling", "cancelled"}:
            job.update({
                "status": "cancelled",
                "finished_at": iso_now(),
                "failure_type": "CANCELLED",
                "process": None,
            })
            return False
        if job.get("status") != "queued":
            return False
        job.update({
            "status": "starting",
            "started_at": iso_now(),
            "command": command_text,
            "log_file": log_path_text,
        })
        return True


def launch_claimed_job(job_id, command, env):
    """Create and register a process without exposing a cancellable gap."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return None
        if job.get("status") in {"cancelling", "cancelled"}:
            job.update({
                "status": "cancelled",
                "finished_at": iso_now(),
                "failure_type": "CANCELLED",
                "process": None,
            })
            return None
        if job.get("status") != "starting":
            return None
        try:
            process = Popen(
                command,
                cwd=get_repo_root(),
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=(os.name != "nt"),
                creationflags=(
                    getattr(__import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0)
                    if os.name == "nt" else 0
                ),
            )
        except Exception:
            job.update({
                "status": "failed",
                "process": None,
                "finished_at": iso_now(),
                "failure_type": "TOOL_FAILURE",
            })
            raise
        job.update({"status": "running", "process": process})
        return process


def request_job_cancellation(job_id) -> dict:
    """Atomically record cancellation and return the process to signal."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return {
                "found": False, "ok": False, "status": None,
                "process": None, "action": None,
            }
        status = job.get("status")
        action = job.get("action")
        if status in {"queued", "starting"}:
            job.update({
                "status": "cancelled",
                "cancel_requested": True,
                "finished_at": iso_now(),
                "failure_type": "CANCELLED",
                "process": None,
            })
            return {
                "found": True, "ok": True, "status": "cancelled",
                "process": None, "action": action,
            }
        if status == "running":
            process = job.get("process")
            if process is None:
                job.update({
                    "status": "failed",
                    "finished_at": iso_now(),
                    "failure_type": "CANCELLATION_FAILED",
                })
                return {
                    "found": True, "ok": False, "status": "failed",
                    "process": None, "action": action,
                }
            job.update({
                "status": "cancelling",
                "cancel_requested": True,
                "cancel_signal_sent": True,
            })
            return {
                "found": True, "ok": True, "status": "cancelling",
                "process": process, "action": action,
            }
        return {
            "found": True, "ok": False, "status": status,
            "process": job.get("process"), "action": action,
        }


def mark_cancellation_failure(job_id, action, message) -> None:
    """Make an unverified cancellation a terminal failure, never a success."""
    with jobs_lock:
        jobs[job_id].update({"status": "failed", "failure_type": "CANCELLATION_FAILED"})
    if action in {"evidence_pipeline", "evidence_batch"}:
        force_evidence_state_terminal(job_id, "failed", message, "CANCELLATION_FAILED")


def classify_evidence_failure(output, returncode=None):
    """Map early process failures to stable machine-readable categories."""
    full_text = "\n".join(output or []).lower()
    if any(token in full_text for token in ("out of memory", "out-of-memory", "memoryerror", "cannot allocate memory", "std::bad_alloc", "oom-kill")):
        return "MEMORY_EXHAUSTED"
    if returncode in {-9, 137} or "sigkill" in full_text:
        return "PROCESS_KILLED"
    if returncode in {-15, 143} or "sigterm" in full_text:
        return "PROCESS_TERMINATED"
    text = "\n".join(line for line in (output or []) if any(marker in line.upper() for marker in ("[FATAL]", "[ERRO]", "[ERROR]", "TRACEBACK"))).lower()
    if "config" in text and any(token in text for token in ("invalid", "inval", "schema", "yaml")):
        return "CONFIG_INVALID"
    if returncode == 65 or any(token in text for token in ("fastq", "fasta", "banco blast", "banco composto", "entrada", "arquivo inexistente", "not found")):
        return "INPUT_INVALID"
    if any(token in text for token in ("artefato", "success.json", "quickcheck", "artifact")):
        return "ARTIFACT_INVALID"
    return "TOOL_FAILURE"


def read_evidence_job_state(run_id):
    """Read only the requested run's state; unusable state is not completion evidence."""
    if not run_id:
        return {}
    try:
        validate_run_id(run_id)
        state = read_state(get_evidence_service().evidence_root / "state" / f"{run_id}.json")
        if state.get("run_id") != run_id or state.get("status") not in RUN_STATUSES:
            return {}
        if any(not isinstance(stage, dict) for stage in state["stages"]):
            return {}
        if state.get("evidence_v2_status", state["status"]) not in RUN_STATUSES | {"not_started"}:
            return {}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}
    return state


def evidence_status_summary(run_id, *, terminal_job=False):
    state = read_evidence_job_state(run_id)
    if not state:
        return {}
    v2_status = state.get("evidence_v2_status", state.get("status", "not_started"))
    official_status = state.get("official_v1_status", "not_started")
    warning = None
    outcome = state.get("analysis_outcome")
    if official_status == "done" and v2_status not in {"done", "done_with_warning"}:
        warning = "A etapa Evidence V2 não foi concluída; resultado V2 NOT_EVALUABLE."
        outcome = outcome or "NOT_EVALUABLE"
    elif v2_status in {"failed", "cancelled", "blocked"}:
        outcome = outcome or "NOT_EVALUABLE"
    summary = {
        "official_v1_status": official_status,
        "evidence_v2_status": v2_status,
        "experimental_warning": warning,
        "experimental_analysis_outcome": outcome,
    }
    if (
        terminal_job
        and state["status"] in TERMINAL_RUN_STATUSES
        and state["status"] == v2_status
    ):
        # Keep the dashboard's existing done + V2 warning representation.
        completed = v2_status in {"done", "done_with_warning"}
        summary.update({
            "status": "done" if completed else state["status"],
            "failure_type": None if completed else state.get("failure_type"),
            "failure_message": None if completed else state.get("failure_message"),
        })
    return summary


def cleanup_old_jobs():
    """Remove expired jobs from in-memory tracking dictionary."""
    with jobs_lock:
        now = time.time()
        to_remove = []
        for job_id, info in jobs.items():
            if info["status"] in TERMINAL_JOB_STATES:
                finished_at = info.get("finished_at")
                if finished_at:
                    try:
                        dt = datetime.fromisoformat(finished_at)
                        if (now - dt.timestamp()) > JOB_TTL_SECONDS:
                            to_remove.append(job_id)
                    except ValueError:
                        pass
        for job_id in to_remove:
            del jobs[job_id]

        if len(jobs) > MAX_JOBS_IN_MEMORY:
            finished = [
                (jid, j) for jid, j in jobs.items()
                if j["status"] in TERMINAL_JOB_STATES
            ]
            finished.sort(key=lambda x: x[1].get("finished_at", ""))
            excess = len(jobs) - MAX_JOBS_IN_MEMORY
            for jid, _ in finished[:excess]:
                del jobs[jid]


def read_tail(path, lines=30):
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return [line.rstrip("\r\n") for line in all_lines[-lines:]]
    except Exception:
        return []


def clamp_output(lines):
    if len(lines) <= MAX_OUTPUT_LINES:
        return lines
    half = MAX_OUTPUT_LINES // 2
    truncated_count = len(lines) - MAX_OUTPUT_LINES
    marker = f"[... {truncated_count} linhas omitidas pelo dashboard ...]"
    return lines[:half] + [marker] + lines[-half:]


def find_blast_path(sample):
    repo_root = get_repo_root()
    candidate = repo_root / "results" / "blast" / f"{sample}_labeled_hits.tsv"
    if candidate.exists():
        return candidate
    candidate_unlabeled = repo_root / "results" / "blast" / f"{sample}_hits.tsv"
    if candidate_unlabeled.exists():
        return candidate_unlabeled
    return None


def find_blast_raw_path(sample):
    repo_root = get_repo_root()
    candidates = sorted(
        (repo_root / "results" / "blast").glob(f"{sample}_*_vs_db.tsv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def find_adjusted_identity_path(sample):
    candidate = get_repo_root() / "results" / "blast" / f"{sample}_adj_identity.tsv"
    return candidate if candidate.exists() else None


def find_hit_contigs_fasta_path(sample):
    repo_root = get_repo_root()
    for suffix in (".fasta", ".fa"):
        candidate = repo_root / "results" / "blast" / f"{sample}_hit_contigs{suffix}"
        if candidate.exists():
            return candidate
    return None


def find_assembly_contigs_path(sample):
    candidate = get_repo_root() / "data" / "assemblies" / f"{sample}_assembly" / "contigs.fa"
    return candidate if candidate.exists() else None


def find_report_path(sample):
    repo_root = get_repo_root()
    for name in (f"{sample}_summary.md", f"{sample}_report.md"):
        candidate = repo_root / "results" / "reports" / name
        if candidate.exists():
            return candidate
    return None


def find_log_path(metadata):
    configured = metadata.get("log_file")
    if configured:
        candidate = Path(configured)
        if candidate.exists():
            return candidate
    run_id = metadata.get("run_id") or metadata.get("id")
    candidates = []
    if run_id:
        candidates.append(LOG_DIR / f"ux_{run_id}.log")
        candidates.append(get_repo_root() / "logs" / f"ux_{run_id}.log")
    sample = metadata.get("sample")
    if sample:
        candidates.append(LOG_DIR / f"{sample}_pipeline.log")
        candidates.append(get_repo_root() / "logs" / f"{sample}_pipeline.log")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_advanced_path(metadata, filename):
    sample = metadata.get("sample")
    params = metadata.get("params") or {}
    kmer = str(params.get("kmer") or 31)
    if not sample:
        return None
    candidate = get_repo_root() / "results" / "phylogeny" / f"{sample}_k{kmer}" / filename
    return candidate if candidate.exists() else None


def find_advanced_report_path(sample):
    repo_root = get_repo_root()
    for name in (f"{sample}_advanced_report.md", f"{sample}_advanced_evidence.md"):
        candidate = repo_root / "results" / "reports" / name
        if candidate.exists():
            return candidate
    return None


def find_assembly_summary_path(sample):
    repo_root = get_repo_root()
    candidate = repo_root / "results" / "assembly" / sample / "assembly_summary.json"
    if candidate.exists():
        return candidate
    return None


def snapshot_run_artifacts(metadata):
    sample = metadata.get("sample")
    run_id = metadata.get("run_id") or metadata.get("id")
    if not run_id:
        return None

    runs_dir = get_runs_dir()
    run_dir = runs_dir / run_id
    staging_dir = runs_dir / ".staging" / run_id
    if staging_dir.exists() or (run_dir / "SUCCESS.json").exists():
        raise FileExistsError(f"run snapshot already exists: {run_id}")
    staging_dir.parent.mkdir(parents=True, exist_ok=True)
    if run_dir.exists():
        # A legacy metadata-only directory is incomplete and non-consumable.
        # Move it under the transaction before adding immutable snapshots.
        os.replace(run_dir, staging_dir)
    else:
        staging_dir.mkdir(parents=True)

    meta_file = staging_dir / "metadata.json"
    atomic_json(meta_file, metadata)

    copied = []
    if sample:
        report_path = (
            find_advanced_report_path(sample)
            if metadata.get("action") == "advanced_analysis"
            else find_report_path(sample)
        )
        targets = [
            (find_blast_raw_path(sample), "blast.tsv"),
            (find_blast_path(sample), "labeled_hits.tsv"),
            (find_adjusted_identity_path(sample), "adj_identity.tsv"),
            (find_hit_contigs_fasta_path(sample), "hit_contigs.fasta"),
            (find_assembly_contigs_path(sample), "assembly_contigs.fa"),
            (report_path, "report.md"),
            (find_advanced_report_path(sample), "advanced_report.md"),
            (find_assembly_summary_path(sample), "assembly_summary.json"),
            (find_log_path(metadata), "run.log"),
            (find_advanced_path(metadata, "alignment.fa"), "advanced_alignment.fa"),
            (find_advanced_path(metadata, "tree.nwk"), "advanced_tree.nwk"),
            (find_advanced_path(metadata, "phylogeny_gate.json"), "advanced_gate.json"),
            (find_advanced_path(metadata, "hits.fa"), "advanced_hits.fa"),
            (find_advanced_path(metadata, "refs.fa"), "advanced_refs.fa"),
            (find_advanced_path(metadata, "hits_summary.tsv"), "advanced_summary.tsv"),
        ]
        if metadata.get("work_root"):
            work = Path(metadata["work_root"])
            targets = [
                (work / "results/blast" / f"{sample}_labeled_hits.tsv", "labeled_hits.tsv"),
                (work / "results/blast" / f"{sample}_adj_identity.tsv", "adj_identity.tsv"),
                (work / "data/assemblies" / f"{sample}_assembly/contigs.fa", "assembly_contigs.fa"),
                (work / "results/reports" / f"{sample}_summary.md", "report.md"),
                (work / "data/assemblies" / f"{sample}_assembly/assembly_summary.json", "assembly_summary.json"),
                (find_log_path(metadata), "run.log"),
            ]
            targets.append((work / "tmp" / f"{sample}.resolved_config.json", "resolved_config.json"))
            targets.extend([
                (work / "results/qc" / f"{sample}_fastp.html", "qc.html"),
                (work / "results/qc" / f"{sample}_fastp.json", "qc.json"),
                (work / "data/cleaned" / f"{sample}_R1.clean.fastq.gz", "cleaned_R1.fastq.gz"),
                (work / "data/cleaned" / f"{sample}_R2.clean.fastq.gz", "cleaned_R2.fastq.gz"),
            ])
        for src, dest_name in targets:
            if src and src.exists():
                dest = staging_dir / dest_name
                try:
                    shutil.copy2(src, dest)
                    copied.append(dest_name)
                except OSError as exc:
                    print(f"[WARN] Falha ao copiar artefato {src} -> {dest}: {exc}")

    manifest_file = staging_dir / "manifest.json"
    manifest_data = {
        "schema_version": "1.0",
        "run_id": run_id,
        "sample": sample,
        "created_at": iso_now(),
        "artifacts": {
            name: {
                "size": (staging_dir / name).stat().st_size,
                "sha256": sha256_file(staging_dir / name),
            }
            for name in ["metadata.json", *copied]
        },
    }
    atomic_json(manifest_file, manifest_data)
    fsync_directory(staging_dir)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging_dir, run_dir)
    fsync_directory(run_dir.parent)
    try:
        atomic_json(run_dir / "SUCCESS.json", {
            "schema_version": "1.0", "id": run_id,
            "status": metadata.get("status") or "done",
            "layer": "operational_1.1",
            "manifest": "manifest.json", "manifest_sha256": sha256_file(run_dir / "manifest.json"),
            "committed_at": iso_now(),
        })
        fsync_directory(run_dir)
    except Exception:
        (run_dir / "SUCCESS.json").unlink(missing_ok=True)
        os.replace(run_dir, staging_dir)
        raise
    return str(run_dir)


def history_artifact_paths(run_dir):
    filenames = {
        "run_report": "report.md",
        "run_log": "run.log",
        "run_blast_tsv": "blast.tsv",
        "run_labeled_hits_tsv": "labeled_hits.tsv",
        "run_adj_identity_tsv": "adj_identity.tsv",
        "run_hit_contigs_fasta": "hit_contigs.fasta",
        "run_assembly_contigs_fasta": "assembly_contigs.fa",
        "run_advanced_alignment": "advanced_alignment.fa",
        "run_advanced_tree": "advanced_tree.nwk",
        "run_advanced_gate": "advanced_gate.json",
        "run_advanced_hits": "advanced_hits.fa",
        "run_advanced_refs": "advanced_refs.fa",
        "run_advanced_summary": "advanced_summary.tsv",
        "run_qc_html": "qc.html", "run_qc_json": "qc.json",
        "run_cleaned_r1": "cleaned_R1.fastq.gz", "run_cleaned_r2": "cleaned_R2.fastq.gz",
    }
    return {
        key: filename
        for key, filename in filenames.items()
        if (run_dir / filename).is_file()
    }


def parse_pipeline_details(params):
    raw = (params.get("pipeline_details") or "").strip()
    if not raw:
        return {}

    parsed = {}
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            return {
                str(k).strip(): str(v).strip()
                for k, v in decoded.items()
                if str(k).strip() and str(v).strip()
            }
    except json.JSONDecodeError:
        pass

    for token in raw.split(";"):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            k, v = token.split("=", 1)
        elif ":" in token:
            k, v = token.split(":", 1)
        else:
            continue
        k = k.strip()
        v = v.strip()
        if k and v:
            parsed[k] = v

    return parsed


def _truthy_flag(value):
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def resolve_dashboard_fastq_path(value):
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("caminho FASTQ vazio")
    if not any(raw.lower().endswith(suffix) for suffix in FASTQ_SUFFIXES):
        raise ValueError("FASTQ deve terminar em .fastq, .fq, .fastq.gz ou .fq.gz")
    windows = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if windows:
        staged = f"/mnt/{windows.group(1).lower()}/{windows.group(2).replace(chr(92), '/')}"
        candidates = (Path(raw), Path(staged))
    else:
        staged = raw.replace("\\", "/")
        relative = Path(staged)
        candidates = (relative, relative if relative.is_absolute() else REPO_ROOT / relative)
    if not any(path.is_file() for path in candidates):
        raise ValueError(f"FASTQ nao encontrado: {raw}")
    return staged


def custom_database_env(params):
    query = str(params.get("db_query") or params.get("query") or "").strip()
    ncbi_db = str(params.get("ncbi_db") or "").strip()

    if not query:
        metadata_path = REPO_ROOT / "db" / "custom" / "metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            metadata = {}
        if metadata.get("db") == "custom":
            query = str(metadata.get("db_query") or "").strip()
            if not ncbi_db:
                ncbi_db = str(metadata.get("ncbi_db") or "").strip()

    if not query:
        raise ValueError(
            "Banco customizado exige uma query NCBI ou metadados de um banco previamente preparado"
        )

    result = {"DB_QUERY": query}
    if ncbi_db:
        result["NCBI_DB"] = ncbi_db
    return result


def assembly_command_args(params):
    """Resolve the dashboard selection without an override on MULTI."""
    selected = str(params.get("assembler") or "spades").strip().lower()
    if selected not in {"velvet", "spades", "metaspades", "consensus", "builder"}:
        raise ValueError("assembler invalido")
    profile = str(params.get("analysis_profile") or params.get("profile") or
                  ("assembly-consensus" if selected == "consensus" else "default")).strip()
    _, resolved = resolve_profile(load_profiles(REPO_ROOT / "config/analysis_profiles.json"), profile)
    if resolved["assembly"]["strategy"] == "consensus":
        if params.get("assembler") and selected != "consensus":
            raise ValueError("Montador individual não pode sobrescrever o perfil MULTI.")
        return ["--analysis-profile", profile]
    if selected == "consensus":
        raise ValueError("MULTI exige o perfil assembly-consensus.")
    return ["--assembler", selected, "--analysis-profile", profile]


def build_command(action, params):
    cmd = []
    env = {}

    db = (params.get("db") or params.get("target") or "").strip().lower()
    if action in {"pipeline", "evidence_pipeline", "evidence_batch"}:
        if not db:
            raise ValueError("A seleção do banco de referência é obrigatória e deve ser feita explicitamente.")
        alias_db = _DB_ALIAS.get(db, db)
        env["DB"] = alias_db
        if alias_db == "custom":
            env.update(custom_database_env(params))

        host_mode = str(params.get("host_filter_mode") or "none").strip().lower()
        if host_mode == "none":
            env["HOST_FILTER_ENABLED"] = "false"
        elif host_mode == "sus_scrofa":
            saved = load_config_env()
            env["HOST_FILTER_ENABLED"] = "true"
            env["HOST_NAME"] = "Sus scrofa"
            env["HOST_INDEX_PREFIX"] = (
                str(params.get("host_index_prefix") or "").strip()
                or (saved.get("HOST_INDEX_PREFIX", "") if saved.get("HOST_NAME", "").strip().lower() == "sus scrofa" else "")
                or str(REPO_ROOT / "ref" / "host" / "sus_scrofa_bt2")
            )
        elif host_mode == "custom":
            host_name = str(params.get("host_name") or "").strip()
            host_index_prefix = str(params.get("host_index_prefix") or "").strip()
            if not host_name or not host_index_prefix:
                raise ValueError(
                    "Filtro customizado exige nome e prefixo do indice Bowtie2 do hospedeiro"
                )
            env["HOST_FILTER_ENABLED"] = "true"
            env["HOST_NAME"] = host_name
            env["HOST_INDEX_PREFIX"] = host_index_prefix
        else:
            raise ValueError(
                "Modo de filtro de hospedeiro invalido; use none, sus_scrofa ou custom"
            )

    if action == "check_env":
        cmd = ["bash", "scripts/ops/check_env.sh"]

    elif action == "demo":
        cmd = ["make", "demo"]

    elif action == "rebuild_env":
        cmd = ["bash", "bundle/install_wsl.sh"]

    elif action == "import_sample":
        sample = validate_sample_id(params["sample"])
        r1 = resolve_dashboard_fastq_path(params.get("r1"))
        r2 = resolve_dashboard_fastq_path(params.get("r2"))
        cmd = ["make", "sample-add", f"ID={sample}", f"R1={r1}", f"R2={r2}"]
        if _truthy_flag(params.get("copy")):
            cmd.append("COPY=1")

    elif action == "pipeline":
        sample = validate_sample_id(params["sample"])
        cmd = [
            "scripts/pipeline/run.sh",
            "--sample", sample,
            *assembly_command_args(params),
        ]
        if params.get("kmer") not in (None, ""):
            cmd.extend(["--kmer", str(params["kmer"])])
        if params.get("skip_qc"):
            cmd.append("--skip-qc")

    elif action == "report":
        sample = validate_sample_id(params["sample"])
        cmd = ["make", "report", f"SAMPLE={sample}"]

    elif action == "evidence_pipeline":
        sample = validate_sample_id(params["sample"])
        run_id = validate_run_id(params.get("run_id") or "dashboard-run-00000000")
        config = str(params.get("config") or "config/evidence_profiles.json").strip()
        token = params.get("reservation_token", "")
        cmd = [
            "scripts/pipeline/run.sh",
            "--sample", sample,
            *assembly_command_args(params),
            "--evidence-v2",
            "--evidence-profiles", config,
        ]
        env["EVIDENCE_RUN_ID"] = run_id
        if params.get("role"):
            role = str(params["role"])
            if role not in {"sample", "positive", "negative_extraction", "negative_library", "negative_sequencing"}:
                raise ValueError("Papel da amostra inválido.")
            env["EVIDENCE_ROLE"] = role
            if role == "positive" and not str(params.get("expected_target") or "").strip():
                raise ValueError("Controle positivo exige um alvo esperado. Informe o alvo antes de iniciar a execução.")
        if params.get("batch_id"):
            env["EVIDENCE_BATCH_ID"] = validate_sample_id(params["batch_id"])
        if params.get("expected_target"):
            env["EVIDENCE_EXPECTED_TARGET"] = str(params["expected_target"])
        if "GENEIN_CONFIG_FILE" not in os.environ:
            env["GENEIN_CONFIG_FILE"] = str(user_config_env_path())
        # The per-run directory below is only the output root. The database is
        # resolved before that swap. DB came from the panel, so BLAST_DB in
        # picornavirus.env (the example ships blastdb/custom) is ignored, the
        # same way Make drops a file path when DB comes from outside the file.
        if "BLAST_DB" not in env and not os.environ.get("BLAST_DB"):
            chosen = resolve_blast_db(env["DB"], os.environ, Path.home(), REPO_ROOT)
            blast_path = Path(chosen)
            if not blast_path.is_absolute():
                blast_path = REPO_ROOT / blast_path
            env["BLAST_DB"] = str(blast_path)
        env["GENEIN_WORK_ROOT"] = str(REPO_ROOT / "results" / "dashboard-work" / run_id)
        raw_dir = REPO_ROOT / "data/raw"
        suffix = ".fastq.gz"
        for candidate in (".fastq.gz", ".fastq", ".fq.gz", ".fq"):
            if all((raw_dir / f"{sample}_R{mate}{candidate}").is_file() for mate in (1, 2)):
                suffix = candidate
                break
        cmd.extend(["--r1", str(raw_dir / f"{sample}_R1{suffix}"),
                    "--r2", str(raw_dir / f"{sample}_R2{suffix}")])
        for key in ("QC_ADAPTER_R1", "QC_ADAPTER_R2"):
            sequence = str(params.get(key.lower()) or "").strip().upper()
            if sequence:
                if not re.fullmatch(r"[ACGTN]{1,500}", sequence):
                    raise ValueError("Adaptador invalido: use a sequencia A/C/G/T/N da biblioteca.")
                env[key] = sequence
        if params.get("kmer") not in (None, ""):
            cmd.extend(["--kmer", str(params["kmer"])])
        if token:
            env["EVIDENCE_RESERVATION_TOKEN"] = token

    elif action == "evidence_batch":
        manifest_id = validate_sample_id(params["manifest_id"])
        run_id = validate_run_id(params.get("run_id") or "dashboard-run-00000000")
        manifest_path = get_evidence_service().manifest_export(manifest_id)
        config = str(params.get("config") or "config/evidence_profiles.json").strip()
        token = params.get("reservation_token", "")
        cmd = [
            "scripts/evidence/run_batch.sh",
            "--batch-manifest", str(manifest_path),
            "--run-id", run_id,
            "--profiles", config,
        ]
        if token:
            env["EVIDENCE_RESERVATION_TOKEN"] = token

    elif action in {"build_db", "db_build"}:
        db_name = (params.get("db") or params.get("target") or "").strip().lower()
        query = (params.get("query") or params.get("db_query") or "").strip()
        taxid = str(params.get("taxid") or "").strip()
        if not query and taxid:
            if not taxid.isdigit():
                raise ValueError("TaxID deve ser numerico.")
            query = f"txid{taxid}[Organism:exp]"
        if (not db_name or db_name == "custom") and query:
            env["DB"] = "custom"
            env["DB_QUERY"] = query
            if params.get("ncbi_db"):
                env["NCBI_DB"] = str(params["ncbi_db"]).strip()
            return ["bash", "scripts/ops/db_manager.sh", "setup"], env
        if not db_name or db_name == "custom":
            raise ValueError("Selecione um banco de referencia ou informe uma query NCBI customizada.")
        alias_db = _DB_ALIAS.get(db_name, db_name)

        target_file = get_repo_root() / "config" / "targets.json"
        known_targets = set()
        if target_file.exists():
            try:
                targets_data = json.loads(target_file.read_text(encoding="utf-8"))
                known_targets = {
                    t.get("id") or t.get("key")
                    for t in targets_data
                    if isinstance(t, dict) and (t.get("id") or t.get("key"))
                }
            except Exception:
                pass

        if alias_db not in known_targets and alias_db not in {"ptv", "evg", "psv", "astrovirus_suino", "picornaviridae_refseq", "picornaviridae_complete", "picornaviridae_all"}:
            raise ValueError(f"Banco nao reconhecido em targets.json: '{db_name}'.")

        cmd = ["make", "db", f"DB={alias_db}"]

    elif action == "advanced_analysis":
        sample = validate_sample_id(params["sample"])
        cmd = ["bash", "scripts/experimental/advanced_analysis/run.sh", "--sample", sample]
        for key, option in (
            ("kmer", "--kmer"),
            ("min_pident", "--min-pident"),
            ("min_aln_len", "--min-aln-len"),
            ("method", "--method"),
            ("threads", "--threads"),
        ):
            value = params.get(key)
            if value not in (None, ""):
                cmd.extend([option, str(value)])

    elif action == "assembly_only":
        sample = validate_sample_id(params["sample"])
        assembler = (params.get("assembler") or "velvet").strip().lower()
        if assembler not in {"velvet", "spades", "metaspades", "builder"}:
            raise ValueError("assembler invalido")
        cmd = [
            "bash", "scripts/experimental/assembly_only/run.sh",
            "--sample", sample, "--assembler", assembler,
        ]
        if params.get("kmer") not in (None, ""):
            cmd.extend(["--kmer", str(params["kmer"])])
        if params.get("spades_params") not in (None, ""):
            cmd.extend(["--spades-params", str(params["spades_params"])])

    elif action == "compare_contigs":
        sample = validate_sample_id(params["sample"])
        comparison_id = validate_run_id(params["comparison_id"])
        source_type = str(params.get("source_type") or "run").strip()
        source_id = safe_id(str(params.get("source_id") or ""), "source_id")
        # Validate the immutable source before the operational job is accepted.
        resolve_source(get_repo_root(), source_type, source_id, sample)
        reference_kind = str(params.get("reference_kind") or "database").strip()
        if reference_kind not in {"database", "panel"}:
            raise ValueError("reference_kind invalido")
        database = safe_name(str(params.get("db") or params.get("database") or ""), "reference_database")
        if reference_kind == "database":
            database = _DB_ALIAS.get(database, database)
        task = str(params.get("blast_task") or "blastn").strip()
        if task not in {"blastn", "blastn-short"}:
            raise ValueError("blast_task invalido")
        word_size = int(params.get("word_size") or (7 if task == "blastn-short" else 11))
        evalue = float(params.get("evalue") or 1e-5)
        max_target_seqs = int(params.get("max_target_seqs") or 50)
        threads = int(params.get("threads") or 4)
        cmd = [
            "bash", "scripts/experimental/contig_comparison/run.sh",
            "--comparison-id", comparison_id, "--sample", sample,
            "--source-type", source_type, "--source-id", source_id,
            "--reference-kind", reference_kind, "--database", database,
            "--blast-task", task, "--word-size", str(word_size),
            "--evalue", str(evalue), "--max-target-seqs", str(max_target_seqs),
            "--threads", str(threads),
        ]
        if params.get("db_query"):
            cmd.extend(["--db-query", str(params["db_query"]).strip()])
        if params.get("ncbi_db"):
            cmd.extend(["--ncbi-db", str(params["ncbi_db"]).strip()])

    else:
        raise ValueError(f"Acao desconhecida: {action}")

    return cmd, env


def run_job(job_id, action, params):
    output_buf = []
    log_file = LOG_DIR / f"ux_{job_id}.log"
    if not claim_job_for_execution(job_id, "", str(log_file)):
        if action in {"evidence_pipeline", "evidence_batch"}:
            force_evidence_state_terminal(
                job_id, "cancelled",
                "Execução cancelada antes da preparação do processo.",
                "CANCELLED",
            )
        return

    env = runtime_environment()

    try:
        env.update(host_env_from_params(params))
    except ValueError as exc:
        with jobs_lock:
            if jobs[job_id].get("status") == "cancelled":
                return
            jobs[job_id].update({
                "status": "failed",
                "output": [f"[ERRO] Parametros de hospedeiro invalidos: {exc}"],
                "finished_at": iso_now(),
                "failure_type": "INPUT_INVALID",
                "failure_message": str(exc),
            })
        if action in {"evidence_pipeline", "evidence_batch"}:
            force_evidence_state_terminal(job_id, "failed", str(exc), "INPUT_INVALID")
        return

    if action in {"pipeline", "evidence_pipeline", "evidence_batch"}:
        p_details = parse_pipeline_details(params)
        for k, v in p_details.items():
            env[k] = str(v)

    try:
        cmd, extra_env = build_command(action, params)
        env.update(extra_env)
        if extra_env.get("GENEIN_WORK_ROOT"):
            Path(extra_env["GENEIN_WORK_ROOT"]).mkdir(parents=True, exist_ok=False)
    except (ValueError, KeyError) as e:
        with jobs_lock:
            if jobs[job_id].get("status") == "cancelled":
                return
            jobs[job_id].update({
                "status": "failed",
                "output": [f"[ERRO] Parametros invalidos: {e}"],
                "finished_at": iso_now(),
                "failure_type": "INPUT_INVALID",
                "failure_message": str(e),
            })
        if action in {"evidence_pipeline", "evidence_batch"}:
            force_evidence_state_terminal(job_id, "failed", str(e), "INPUT_INVALID")
        return

    adapter_assignments = [f"{key}={shlex.quote(extra_env[key])}" for key in ("QC_ADAPTER_R1", "QC_ADAPTER_R2") if key in extra_env]
    command_text = " ".join([*adapter_assignments, shlex.join(cmd)])
    with jobs_lock:
        status_before_launch = jobs[job_id].get("status")
        can_launch = status_before_launch == "starting"
        if can_launch:
            jobs[job_id]["command"] = command_text
    if not can_launch:
        if (
            status_before_launch == "cancelled"
            and action in {"evidence_pipeline", "evidence_batch"}
        ):
            force_evidence_state_terminal(
                job_id, "cancelled",
                "Execução cancelada antes do lançamento do processo.",
                "CANCELLED", command_text,
            )
        return

    try:
        popener = launch_claimed_job(job_id, cmd, env)
        if popener is None:
            if action in {"evidence_pipeline", "evidence_batch"}:
                force_evidence_state_terminal(
                    job_id, "cancelled",
                    "Execução cancelada durante a transição de lançamento.",
                    "CANCELLED", command_text,
                )
            return
    except Exception as exc:
        msg = f"[ERRO] Falha ao iniciar processo: {exc}"
        with jobs_lock:
            jobs[job_id].update({
                "status": "failed",
                "output": [msg],
                "finished_at": iso_now(),
                "failure_type": "TOOL_FAILURE",
                "failure_message": str(exc),
            })
        if action in {"evidence_pipeline", "evidence_batch"}:
            force_evidence_state_terminal(job_id, "failed", str(exc), "TOOL_FAILURE", command_text)
        return

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as lf:
            for line in popener.stdout:
                line_clean = line.rstrip("\r\n")
                lf.write(line)
                lf.flush()
                output_buf.append(line_clean)

                with jobs_lock:
                    jobs[job_id]["output"] = clamp_output(list(output_buf))
                    state_match = re.match(r"^\[CONTIG_COMPARE\]\[STATE\]\s+([a-z_]+)$", line_clean)
                    if state_match:
                        jobs[job_id]["stage_status"] = state_match.group(1)
                    if (
                        jobs[job_id].get("cancel_requested")
                        and not jobs[job_id].get("cancel_signal_sent")
                    ):
                        jobs[job_id]["cancel_signal_sent"] = True
                        signaled, err_msg = terminate_process_group(popener, getattr(signal, "SIGTERM", signal.SIGINT))
                        if not signaled:
                            jobs[job_id]["output"].append(f"[WARN] {err_msg}")
                            terminate_process_group(popener, getattr(signal, "SIGKILL", signal.SIGINT))

        popener.wait()
        rc = popener.returncode

        with jobs_lock:
            jobs[job_id]["process"] = None
            jobs[job_id]["finished_at"] = iso_now()
            jobs[job_id]["exit_code"] = rc
            jobs[job_id]["returncode"] = rc

            if jobs[job_id].get("cancel_requested"):
                # A non-interruptible finalize can commit before observing the
                # cancellation and still exit 130. The matching terminal state
                # wins over the request/return code; do not terminalize it again.
                summary = evidence_status_summary(job_id, terminal_job=True) if action in {
                    "evidence_pipeline", "evidence_batch",
                } else {}
                if summary.get("status") in TERMINAL_JOB_STATES:
                    jobs[job_id].update(summary)
                elif rc == 0:
                    jobs[job_id].update({"status": "failed", "failure_type": "CANCELLATION_FAILED"})
                    if action in {"evidence_pipeline", "evidence_batch"}:
                        force_evidence_state_terminal(
                            job_id, "failed",
                            "O processo concluiu normalmente apesar do pedido de cancelamento",
                            "CANCELLATION_FAILED", command_text,
                        )
                else:
                    jobs[job_id].update({"status": "cancelled", "failure_type": "CANCELLED"})
                    if action == "compare_contigs":
                        finalize_contig_comparison_cancellation(
                            get_repo_root(), params["comparison_id"],
                            "Execucao cancelada pelo usuario apos termino do processo",
                        )
                    if action in {"evidence_pipeline", "evidence_batch"}:
                        force_evidence_state_terminal(
                            job_id, "cancelled", "Execucao cancelada pelo usuario",
                            "CANCELLED", command_text,
                        )
            elif rc == 0:
                jobs[job_id]["status"] = "done"
                if action in {"evidence_pipeline", "evidence_batch"}:
                    summary = evidence_status_summary(job_id)
                    jobs[job_id].update(summary)
                    v2_status = summary.get("evidence_v2_status")
                    if v2_status not in {"done", "done_with_warning"}:
                        jobs[job_id]["status"] = "partial"
                        jobs[job_id]["failure_type"] = "EVIDENCE_V2_INCOMPLETE"
                if action in {"pipeline", "evidence_pipeline", "advanced_analysis", "assembly_only"}:
                    sample = params.get("sample", "")
                    snapshot_metadata = {
                        "id": job_id,
                        "run_id": job_id,
                        "sample": sample,
                        "action": action,
                        "params": params,
                        "work_root": extra_env.get("GENEIN_WORK_ROOT"),
                        "started_at": jobs[job_id].get("started_at"),
                        "finished_at": jobs[job_id]["finished_at"],
                        "command": command_text,
                        "log_file": str(log_file),
                        "status": jobs[job_id]["status"],
                        "layer": "operational_1.1",
                    }
                    run_dir = snapshot_run_artifacts(snapshot_metadata)
                    jobs[job_id]["run"] = {
                        "run_dir": Path(run_dir).name if run_dir else job_id,
                        "sample": sample,
                        "paths": history_artifact_paths(Path(run_dir)) if run_dir else {},
                    }
                elif action == "compare_contigs":
                    comparison_id = params["comparison_id"]
                    comparison = next(
                        (item for item in list_comparisons(get_repo_root()) if item["comparison_id"] == comparison_id),
                        None,
                    )
                    if comparison is None:
                        raise RuntimeError("comparacao concluiu sem artefato promovido valido")
                    jobs[job_id]["run"] = comparison
            else:
                failure_type = classify_evidence_failure(output_buf, rc)
                failure_message = {
                    "MEMORY_EXHAUSTED": "Falta de memória durante o processamento. Libere memória antes de repetir.",
                    "PROCESS_KILLED": "Processo morto por SIGKILL. Pode ter sido encerrado pelo sistema por falta de memória ou por uma ação externa; confira o log do sistema.",
                    "PROCESS_TERMINATED": "Processo interrompido por SIGTERM (sinal de término externo).",
                }.get(failure_type, f"Processo encerrou com código de erro {rc}")
                jobs[job_id].update({
                    "status": "failed",
                    "failure_type": failure_type,
                    "failure_message": failure_message,
                })
                if action in {"evidence_pipeline", "evidence_batch"}:
                    joined_output = "\n".join(output_buf)
                    explicit_stage = None
                    if rc == 65 or ("[DATABASE_PREFLIGHT]" in joined_output and "[FATAL]" in joined_output):
                        explicit_stage = "database_preflight"
                    force_evidence_state_terminal(
                        job_id, "failed",
                        failure_message,
                        failure_type, command_text,
                        failed_stage=explicit_stage,
                    )
            atomic_json(LOG_DIR / f"ux_{job_id}.exit.json", {"returncode": rc})
            if rc != 0 and action == "evidence_pipeline" and jobs[job_id]["status"] in {"failed", "cancelled"} and extra_env.get("GENEIN_WORK_ROOT"):
                run_dir = snapshot_run_artifacts({
                    "id": job_id, "run_id": job_id, "sample": params["sample"],
                    "action": action, "params": params, "status": jobs[job_id]["status"],
                    "partial": True, "work_root": extra_env.get("GENEIN_WORK_ROOT"),
                    "log_file": str(log_file), "finished_at": jobs[job_id]["finished_at"],
                })
                jobs[job_id]["run"] = {"run_dir": Path(run_dir).name, "paths": history_artifact_paths(Path(run_dir))}

    except Exception as exc:
        logging.exception(f"Exceção não tratada na execução do job {job_id}")
        with jobs_lock:
            jobs[job_id]["process"] = None
            jobs[job_id].update({
                "status": "failed",
                "output": clamp_output(list(output_buf) + [f"[ERRO EXCECAO] {exc}"]),
                "finished_at": iso_now(),
                "failure_type": "TOOL_FAILURE",
                "failure_message": str(exc),
            })
        if action in {"evidence_pipeline", "evidence_batch"}:
            force_evidence_state_terminal(job_id, "failed", str(exc), "TOOL_FAILURE", command_text)


def _history_epoch(value):
    """Convert an ISO timestamp to a sortable epoch without failing history."""
    if not value:
        return 0
    try:
        normalized = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0


def list_run_history():
    runs = []
    seen_ids = set()
    # History is called through the compatibility facade, which temporarily
    # redirects this module's service/root for isolated callers and tests.
    service = EVIDENCE_SERVICE
    repo_root = get_repo_root()
    runs_dir = get_runs_dir()
    evidence_root = getattr(service, "evidence_root", None) or (repo_root / "results" / "evidence")
    state_dir = evidence_root / "state"
    if state_dir.exists():
        for state_file in state_dir.glob("*.json"):
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            run_id = state.get("run_id")
            if not run_id:
                continue
            seen_ids.add(run_id)
            status = state.get("status", "failed")
            try:
                inspection = service.inspect_run(str(run_id))
            except (AttributeError, FileNotFoundError, ValueError):
                inspection = {
                    "status": "INCOMPLETE", "valid_alpha2": False, "complete": False,
                    "message": "Execução Evidence V2 incompleta.",
                }
            evidence_v2_status = state.get("evidence_v2_status", status)
            finished_at = state.get("finished_at")
            if inspection["valid_alpha2"]:
                display_status = evidence_v2_status
            elif inspection["status"] == "INCOMPLETE":
                display_status = evidence_v2_status
            else:
                display_status = inspection["status"].lower()
            official_v1_status = state.get("official_v1_status", "not_started")
            experimental_warning = None
            if official_v1_status == "done" and evidence_v2_status not in {"done", "done_with_warning"}:
                experimental_warning = "A etapa Evidence V2 ficou NOT_EVALUABLE."
            snapshot_metadata = {}
            process_returncode = state.get("exit_code")
            try:
                process_returncode = json.loads((LOG_DIR / f"ux_{run_id}.exit.json").read_text())["returncode"]
            except (OSError, ValueError, KeyError):
                pass
            try:
                snapshot_metadata = json.loads((runs_dir / run_id / "metadata.json").read_text())
            except (OSError, ValueError):
                pass
            effective_config = {}
            try:
                resolved = json.loads((runs_dir / run_id / "resolved_config.json").read_text())
                effective_config = {key: resolved[key] for key in ("db", "assembler", "analysis_profile", "host_filter_enabled", "host_name", "host_index_prefix", "qc_adapter_r1", "qc_adapter_r2") if key in resolved}
            except (OSError, ValueError):
                pass
            runs.append({
                "id": run_id, "run_id": run_id,
                "run_dir": run_id if (runs_dir / run_id / "SUCCESS.json").is_file() else "",
                "paths": history_artifact_paths(runs_dir / run_id),
                "params": snapshot_metadata.get("params", {}),
                "effective_config": effective_config,
                "label": snapshot_metadata.get("params", {}).get("label", ""),
                "action": state.get("action"), "sample": ", ".join(state.get("sample_ids") or []),
                "batch_id": state.get("batch_id"), "start": state.get("started_at") or state.get("created_at"),
                "end": finished_at, "end_epoch": _history_epoch(finished_at),
                "exit_code": jobs.get(run_id, {}).get("returncode", process_returncode),
                "status": display_status, "shadow_mode": state.get("shadow_mode"), "evidence_v2": True,
                "valid_alpha2": inspection["valid_alpha2"],
                "compatibility_status": inspection["status"],
                "compatibility_message": inspection["message"],
                "job_status": "done" if official_v1_status == "done" else official_v1_status,
                "official_v1_status": official_v1_status,
                "evidence_v2_status": evidence_v2_status,
                "experimental_warning": experimental_warning,
                "failure_type": state.get("failure_type"),
                "failed_stage": state.get("failed_stage"),
                "failure_message": state.get("failure_message"),
                "complete": inspection["complete"],
            })

    if runs_dir.exists():
        for item in runs_dir.iterdir():
            if not item.is_dir() or item.name in seen_ids or item.name.startswith("evidence"):
                continue
            run_json = item / "run.json"
            meta_file = item / "metadata.json"
            if run_json.exists():
                try:
                    data = json.loads(run_json.read_text(encoding="utf-8"))
                    if data.get("action", "").startswith("evidence"):
                        continue
                    runs.append({
                        "id": item.name, "run_id": item.name, "run_dir": item.name,
                        "action": data.get("action"), "sample": data.get("sample"),
                        "start": data.get("start"), "end": data.get("end"),
                        "end_epoch": data.get("end_epoch", 0),
                        "status": "done",
                        "paths": history_artifact_paths(item),
                    })
                except Exception:
                    pass

            elif meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    if meta.get("action", "").startswith("evidence"):
                        continue
                    runs.append({
                        "id": item.name, "run_id": item.name, "run_dir": item.name,
                        "action": meta.get("action"), "sample": meta.get("sample"),
                        "start": meta.get("started_at") or meta.get("created_at"),
                        "end": meta.get("finished_at"),
                        "end_epoch": _history_epoch(meta.get("finished_at")),
                        "status": meta.get("status", "done"),
                        "paths": history_artifact_paths(item),
                    })
                except Exception:
                    pass

    for comparison in list_comparisons(repo_root):
        completed_at = comparison.get("completed_at")
        runs.append({
            "id": comparison["comparison_id"], "run_id": comparison["comparison_id"],
            "run_dir": comparison["comparison_id"], "action": "compare_contigs",
            "sample": comparison.get("sample"), "start": comparison.get("created_at"),
            "end": completed_at, "end_epoch": _history_epoch(completed_at), "status": "done",
            "exit_code": 0, "contigs_source_run": comparison.get("contigs_source_run"),
            "contigs_source_id": comparison.get("contigs_source_id"),
            "reference_database": comparison.get("reference_database"),
            "comparison": True,
        })

    runs.extend(_external_output_runs(seen_ids))
    runs.sort(key=lambda item: item.get("end_epoch", 0), reverse=True)
    return runs


def _receipt_sample(receipt):
    """CLI receipts name the sample. Older files only carry it in the command."""
    sample = receipt.get("sample")
    if isinstance(sample, str) and sample.strip():
        return sample.strip()
    command = receipt.get("command")
    if isinstance(command, list):
        for index, token in enumerate(command):
            if token == "--sample" and index + 1 < len(command):
                nxt = command[index + 1]
                if isinstance(nxt, str) and nxt.strip() and not nxt.startswith("-"):
                    return nxt.strip()
    return ""


def _external_output_runs(seen_ids):
    """List CLI receipts under GENEIN_OUTPUT_ROOT. Unset leaves history unchanged."""
    raw = os.environ.get("GENEIN_OUTPUT_ROOT", "").strip()
    if not raw:
        return []
    root = Path(raw).expanduser()
    if not root.is_dir():
        return []
    folders = []
    if (root / "execution.json").is_file():
        folders.append(root)
    else:
        try:
            children = sorted(path for path in root.iterdir() if path.is_dir())
        except OSError:
            children = []
        folders.extend(child for child in children if (child / "execution.json").is_file())
    status_map = {"completed": "done", "running": "running", "cancelled": "cancelled", "failed": "failed"}
    found = []
    for folder in folders:
        try:
            receipt = json.loads((folder / "execution.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if not isinstance(receipt, dict):
            continue
        run_id = str(receipt.get("run_id") or folder.name)
        if not run_id or run_id in seen_ids:
            continue
        seen_ids.add(run_id)
        finished = receipt.get("finished_at")
        found.append({
            "id": run_id,
            "run_id": run_id,
            "run_dir": "",
            "output_root": str(folder),
            "action": "genein_run",
            "sample": _receipt_sample(receipt),
            "start": receipt.get("started_at"),
            "end": finished,
            "end_epoch": _history_epoch(finished),
            "status": status_map.get(receipt.get("status"), receipt.get("status") or "unavailable"),
            "label": str(folder),
            "external_output": True,
        })
    return found


def resolve_history_file(run_dir, file_type):
    targets = {
        "report": "report.md",
        "advanced_report": "advanced_report.md",
        "log": "run.log",
        "blast": "blast.tsv",
        "labeled": "labeled_hits.tsv",
        "blast_tsv": "labeled_hits.tsv",
        "adj_identity": "adj_identity.tsv",
        "hit_contigs_fasta": "hit_contigs.fasta",
        "hit_contigs": "hit_contigs.fasta",
        "assembly_contigs_fasta": "assembly_contigs.fa",
        "run_advanced_alignment": "advanced_alignment.fa",
        "run_advanced_tree": "advanced_tree.nwk",
        "run_advanced_gate": "advanced_gate.json",
        "run_advanced_hits": "advanced_hits.fa",
        "run_advanced_refs": "advanced_refs.fa",
        "run_advanced_summary": "advanced_summary.tsv",
        "assembly_summary": "assembly_summary.json",
        "sample_evidence": "sample_evidence.json",
        "qc_html": "qc.html", "qc_json": "qc.json",
        "cleaned_r1": "cleaned_R1.fastq.gz", "cleaned_r2": "cleaned_R2.fastq.gz",
    }
    filename = targets.get(file_type)
    if not filename:
        return None
    runs_dir = get_runs_dir().resolve()
    try:
        run_path = (runs_dir / str(run_dir)).resolve()
        run_path.relative_to(runs_dir)
    except (OSError, ValueError):
        return None
    candidate = run_path / filename
    return candidate if candidate.is_file() else None
