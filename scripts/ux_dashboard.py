#!/usr/bin/env python3
"""
Gene-In UX Dashboard Entry Point & Public Facade
Ponto de entrada local e fachada de compatibilidade para o subpacote `scripts.dashboard`.
"""

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "experimental" / "contig_comparison"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Import standard dashboard components
from dashboard.config import (
    REPO_ROOT, DASHBOARD_DIR, LOG_DIR, RUNS_DIR, TARGETS_FILE,
    CONFIG_ENV_PRIMARY, CONFIG_ENV_EXAMPLE, CONFIG_ENV_LEGACY,
    ENVIRONMENT_YML, INSTALL_WSL_SCRIPT, JAVASCRIPT_MODULES,
    BUNDLE_ENV_BIN,
    PREFLIGHT_TOOLS, ASSEMBLER_TOOLS, SUPPORTED_ENV_KEYS, _DB_ALIAS,
    require_sample_id, iso_now, is_loopback_host, get_preflight_status,
    list_targets, list_db_profiles, get_config_env_path, parse_env_file,
    load_config_env, validate_config_updates,
    validate_host_index, host_env_from_params, get_environment_status, tool_versions,
    runtime_environment,
)
from dashboard.jobs import (
    EVIDENCE_SERVICE, jobs, jobs_lock, MAX_OUTPUT_LINES, JOB_TTL_SECONDS,
    MAX_JOBS_IN_MEMORY, MAX_RUNNING_JOBS, ACTIVE_JOB_STATES,
    TERMINAL_JOB_STATES, initialize_evidence_dashboard_state,
    force_evidence_state_terminal, terminate_process_group, mark_cancellation_failure,
    claim_job_for_execution, launch_claimed_job, request_job_cancellation,
    classify_evidence_failure, evidence_status_summary, cleanup_old_jobs,
    read_tail, clamp_output, find_blast_path, find_hit_contigs_fasta_path,
    find_report_path, find_advanced_report_path, find_assembly_summary_path,
    snapshot_run_artifacts, parse_pipeline_details, build_command, run_job,
    resolve_history_file, Popen,
)
from dashboard.handler import (
    logger, CACHE_BYPASS_CONTENT_TYPES, MAX_UPLOAD_BYTES,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES, sanitize_token, sanitize_for_log,
    params_for_log, command_for_log, json_response, request_content_length,
    text_response, serve_file, list_samples, cleanup_temp_files,
    import_zip_sample, DashboardHandler, query_one,
)
from dashboard.server import _ensure_config_env, run_server


def save_config_env(updates):
    import dashboard.config as _cfg
    orig = _cfg.CONFIG_ENV_PRIMARY
    _cfg.CONFIG_ENV_PRIMARY = CONFIG_ENV_PRIMARY
    try:
        return _cfg.save_config_env(updates)
    finally:
        _cfg.CONFIG_ENV_PRIMARY = orig


def import_uploaded_files(sample, r1_name, r1_data, r2_name, r2_data, replace=False):
    import dashboard.handler as _hnd
    orig = _hnd.REPO_ROOT
    _hnd.REPO_ROOT = REPO_ROOT
    try:
        return _hnd.import_uploaded_files(sample, r1_name, r1_data, r2_name, r2_data, replace=replace)
    finally:
        _hnd.REPO_ROOT = orig


def list_run_history():
    import dashboard.jobs as _jobs
    import dashboard.config as _cfg
    orig_runs = _jobs.RUNS_DIR
    orig_root = _jobs.REPO_ROOT
    orig_cfg_root = _cfg.REPO_ROOT
    orig_cfg_runs = _cfg.RUNS_DIR
    orig_service = _jobs.EVIDENCE_SERVICE
    _jobs.RUNS_DIR = RUNS_DIR
    _jobs.REPO_ROOT = REPO_ROOT
    _cfg.REPO_ROOT = REPO_ROOT
    _cfg.RUNS_DIR = RUNS_DIR
    _jobs.EVIDENCE_SERVICE = EVIDENCE_SERVICE
    try:
        return _jobs.list_run_history()
    finally:
        _jobs.RUNS_DIR = orig_runs
        _jobs.REPO_ROOT = orig_root
        _cfg.REPO_ROOT = orig_cfg_root
        _cfg.RUNS_DIR = orig_cfg_runs
        _jobs.EVIDENCE_SERVICE = orig_service


if __name__ == "__main__":
    run_server()
