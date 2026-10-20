import json

import pytest
from scripts.dashboard.jobs import classify_evidence_failure, force_evidence_state_terminal
from scripts.dashboard import jobs as dashboard_jobs
from scripts.evidence.common import write_json_atomic
from scripts.evidence.run_state import FAILURE_TYPES, initial_state, set_stage


@pytest.mark.parametrize('lines,code,expected', [
    ([], -9, 'PROCESS_KILLED'), ([], 137, 'PROCESS_KILLED'),
    ([], -15, 'PROCESS_TERMINATED'), ([], 143, 'PROCESS_TERMINATED'),
    (["subprocess.CalledProcessError: blastn died with <Signals.SIGKILL: 9>"], 1, 'PROCESS_KILLED'),
    (["blastn died with <Signals.SIGTERM: 15>"], 1, 'PROCESS_TERMINATED'),
    (["terminate: std::bad_alloc: Cannot allocate memory"], 1, 'MEMORY_EXHAUSTED'),
    (["MemoryError"], 1, 'MEMORY_EXHAUSTED'),
    (["terminate: std::bad_alloc"], 1, 'MEMORY_EXHAUSTED'),
    (["[FATAL] FASTQ inválido"], 1, 'INPUT_INVALID'),
    (["[FATAL] ferramenta falhou"], 1, 'TOOL_FAILURE'),
])
def test_failure_cause_survives_shell_wrapper(lines, code, expected):
    assert classify_evidence_failure(lines, code) == expected
    assert expected in FAILURE_TYPES


def test_database_preflight_does_not_become_quality_control(tmp_path, monkeypatch):
    run_id = "dbpreflight01"
    evidence = tmp_path / "evidence"
    state_path = evidence / "state" / f"{run_id}.json"
    state = initial_state(run_id, "evidence_single", ["amostra"], None)
    set_stage(state, "input_validation", "done", "entrada validada")
    state["status"] = "running"
    state["started_at"] = state["created_at"]
    write_json_atomic(state_path, state)

    class _Service:
        evidence_root = evidence

    monkeypatch.setattr(dashboard_jobs, "get_evidence_service", lambda: _Service())
    dashboard_jobs.jobs[run_id] = {"command": "bash scripts/pipeline/run.sh"}
    try:
        force_evidence_state_terminal(
            run_id, "failed",
            "Banco composto sem manifesto. Prepare o banco antes de executar.",
            "INPUT_INVALID", "bash scripts/pipeline/run.sh",
            failed_stage="database_preflight",
        )
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved["failed_stage"] == "database_preflight"
        quality = next(item for item in saved["stages"] if item["id"] == "quality_control")
        assert quality["status"] == "pending"
    finally:
        dashboard_jobs.jobs.pop(run_id, None)
