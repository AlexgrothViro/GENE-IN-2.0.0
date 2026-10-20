"""Batch behavior with real contract helpers and controlled sample processes."""
import csv
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from genein.pipeline.batch import main, metrics_root
from genein.pipeline.sample import BatchCancelled, ProcessRunner

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "posix", reason="Pipeline adapters require POSIX shell/process groups")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def batch_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo with spaces"
    (repo / "scripts/pipeline").mkdir(parents=True)
    for name in ("evidence", "lib"):
        (repo / "scripts" / name).symlink_to(ROOT / "scripts" / name, target_is_directory=True)
    (repo / "config").symlink_to(ROOT / "config", target_is_directory=True)
    (repo / "scripts/pipeline/run_sample.sh").write_text(
        '#!/usr/bin/env bash\nexec python3 "$GENEIN_TEST_SOURCE/scripts/tests/fixtures/batch_child.py" "$@"\n')
    manifest = repo / "manifest.tsv"
    with manifest.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["batch_id", "sample_id", "role", "library_mode", "umi_mode", "r1", "r2", "expected_target"])
        for sample, role in (("sample-a", "sample"), ("sample-b", "negative_extraction")):
            for mate in (1, 2):
                (repo / f"{sample}_{mate}.fq").write_text(f"@read/{mate}\nACGT\n+\nIIII\n")
            writer.writerow(["batch-a", sample, role, "shotgun", "none",
                             f"{sample}_1.fq", f"{sample}_2.fq", ""])
    monkeypatch.setenv("GENEIN_TEST_SOURCE", str(ROOT))
    monkeypatch.setenv("GENEIN_TEST_REPO", str(repo))
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.delenv("EVIDENCE_RESERVATION_TOKEN", raising=False)
    # The user guide exports GENEIN_WORK_ROOT for reference data. That directory
    # is not where this fixture writes QC reports.
    foreign = tmp_path / "exported-work-root"
    foreign.mkdir()
    monkeypatch.setenv("GENEIN_WORK_ROOT", str(foreign))
    return repo


def arguments(repo):
    return ["--batch-manifest", str(repo / "manifest.tsv"), "--run-id", "batch-run",
            "--threads", "3", "--evidence-root", str(repo / "evidence")]


def test_metrics_root_uses_work_root_only_when_the_qc_report_is_there(tmp_path):
    repo = tmp_path / "repo"
    work = tmp_path / "output"
    (work / "results" / "qc").mkdir(parents=True)
    (work / "results" / "qc" / "sample-a_fastp.json").write_text("{}\n", encoding="utf-8")
    assert metrics_root(repo, str(work), "sample-a") == work
    assert metrics_root(repo, str(tmp_path / "missing"), "sample-a") == repo
    assert metrics_root(repo, None, "sample-a") == repo


def test_two_samples_controls_and_commits_are_transactional(batch_repo, monkeypatch):
    repo = batch_repo
    monkeypatch.setenv("DB", "custom-db")
    monkeypatch.setenv("HOST_FILTER_ENABLED", "false")
    monkeypatch.setenv("SEARCH_PROFILES", "A,C")
    monkeypatch.setenv("EVIDENCE_RUN_ID", "inherited-parent")
    profiles = repo / "selected profiles.json"
    shutil.copyfile(ROOT / "config/evidence_profiles.json", profiles)
    assert main([*arguments(repo), "--profiles", str(profiles)], repo_root=repo) == 0
    final = repo / "evidence/runs/batch-run"
    assert read(final / "SUCCESS.json")["sample_count"] == 2
    assert read(repo / "evidence/state/batch-run.json")["status"] == "done"
    assert not (repo / "evidence/.staging/batch-run").exists()
    for sample, role in (("sample-a", "sample"), ("sample-b", "negative_extraction")):
        record = read(repo / f"{sample}.invocation.json")
        assert record["args"]["threads"] == "3"
        assert record["args"]["evidence_v2"] is True
        assert record["args"]["evidence_profiles"] == str(profiles)
        env = record["env"]
        assert env["EVIDENCE_RUN_ID"] == f"batch-run-{sample}"
        assert env["EVIDENCE_BATCH_ID"] == "batch-a"
        assert env["EVIDENCE_RESERVATION_TOKEN"] == ""
        assert env["EVIDENCE_ROLE"] == role
        assert env["EVIDENCE_LIBRARY_MODE"] == "shotgun"
        assert env["EVIDENCE_UMI_MODE"] == "none"
        assert env["EVIDENCE_EXPECTED_TARGET"] == ""
        assert env["SAMPLE_R1"] == str(repo / f"{sample}_1.fq")
        assert env["SAMPLE_R2"] == str(repo / f"{sample}_2.fq")
        assert (env["DB"], env["HOST_FILTER_ENABLED"], env["SEARCH_PROFILES"]) == ("custom-db", "false", "A,C")
        source = repo / "evidence/runs" / f"batch-run-{sample}"
        copied = final / "samples" / sample
        assert "SOURCE_SUCCESS.json" in [p.name for p in copied.iterdir()]
        assert read(source / "sample_evidence.json")["controls"]["status"] == "UNCONTROLLED"
        assert read(copied / "SUCCESS.json")["parent_run_id"] == "batch-run"
        if role == "negative_extraction":
            assert read(copied / "sample_evidence.json")["controls"]["status"] == "CONTROL_NOT_APPLICABLE"
        # Existing integrity verifier checks hashes, policy identity and artifacts.
        result = subprocess.run([sys.executable, ROOT / "scripts/evidence/validate_run_artifacts.py",
                                 "--dir", source], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    assert read(final / "batch_evidence.json")["batch_id"] == "batch-a"


def test_batch_never_spawns_run_state_as_a_subprocess(batch_repo, monkeypatch):
    """GEN-005F3A: state.json mutations happen in-process via genein.pipeline.state_api;
    scripts/evidence/run_state.py must never be launched as a child process."""
    repo = batch_repo
    spawned_scripts = []
    run = ProcessRunner.run

    def spy(self, command, **kwargs):
        args = [str(arg) for arg in command]
        if len(args) > 1:
            spawned_scripts.append(Path(args[1]).name)
        return run(self, command, **kwargs)

    with patch.object(ProcessRunner, "run", spy):
        assert main(arguments(repo), repo_root=repo) == 0
    assert "run_state.py" not in spawned_scripts
    assert spawned_scripts  # the spy actually observed real subprocess calls
    assert read(repo / "evidence/state/batch-run.json")["status"] == "done"

    # The interrupted()/failure path must also stay subprocess-free.
    spawned_scripts.clear()
    monkeypatch.setenv("GENEIN_TEST_FAIL", "sample-b")
    with patch.object(ProcessRunner, "run", spy):
        assert main([*arguments(repo), "--run-id", "batch-run-2"], repo_root=repo) == 23
    assert "run_state.py" not in spawned_scripts
    assert read(repo / "evidence/state/batch-run-2.json")["status"] == "failed"


def test_failed_second_child_keeps_first_and_batch_staging(batch_repo, monkeypatch):
    monkeypatch.setenv("GENEIN_TEST_FAIL", "sample-b")
    assert main(arguments(batch_repo), repo_root=batch_repo) == 23
    root = batch_repo / "evidence"
    assert read(root / "state/batch-run.json")["status"] == "failed"
    assert (root / "runs/batch-run-sample-a/SUCCESS.json").exists()
    assert (root / ".staging/batch-run/samples/sample-a/SUCCESS.json").exists()
    assert not (root / "runs/batch-run").exists()
    assert not (root / ".staging/batch-run/SUCCESS.json").exists()


def test_zero_exit_child_without_commit_cannot_promote_batch(batch_repo, monkeypatch):
    monkeypatch.setenv("GENEIN_TEST_INCOMPLETE", "sample-b")
    assert main(arguments(batch_repo), repo_root=batch_repo) != 0
    assert not (batch_repo / "evidence/runs/batch-run").exists()
    assert read(batch_repo / "evidence/state/batch-run.json")["status"] == "failed"


def reserve(repo, token):
    subprocess.run([sys.executable, ROOT / "scripts/evidence/run_state.py",
                    "--state", repo / "evidence/state/batch-run.json", "reserve",
                    "--run-id", "batch-run", "--action", "evidence_batch", "--batch-id", "batch-a",
                    "--sample", "sample-a", "--sample", "sample-b", "--reservation-token", token], check=True)


def test_dashboard_reservation_is_adopted_and_token_not_inherited(batch_repo, monkeypatch):
    token = "dashboard-token-" + "a" * 32
    reserve(batch_repo, token)
    monkeypatch.setenv("EVIDENCE_RESERVATION_TOKEN", token)
    assert main(arguments(batch_repo), repo_root=batch_repo) == 0
    assert read(batch_repo / "sample-a.invocation.json")["env"]["EVIDENCE_RESERVATION_TOKEN"] == ""
    assert read(batch_repo / "evidence/state/batch-run.json")["reservation"]["status"] == "claimed"


@pytest.mark.parametrize("token", ["", "wrong-token-" + "b" * 32])
def test_foreign_reservation_is_not_mutated(batch_repo, monkeypatch, token):
    reserve(batch_repo, "owner-token-" + "a" * 32)
    state = batch_repo / "evidence/state/batch-run.json"
    before = state.read_bytes()
    monkeypatch.setenv("EVIDENCE_RESERVATION_TOKEN", token)
    assert main(arguments(batch_repo), repo_root=batch_repo) != 0
    assert state.read_bytes() == before
    assert not (batch_repo / "sample-a.invocation.json").exists()
    assert list((batch_repo / "evidence/.staging").iterdir()) == []


def alive(pid):
    status = Path(f"/proc/{pid}/stat")
    return status.exists() and status.read_text().split()[2] != "Z"


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_cancellation_stops_grandchildren_and_preserves_staging(batch_repo, monkeypatch, sig):
    monkeypatch.setenv("GENEIN_TEST_WAIT", "sample-b")
    code = "from pathlib import Path; from genein.pipeline.batch import main; import sys; sys.exit(main(sys.argv[2:], repo_root=Path(sys.argv[1])))"
    log = batch_repo / "cancel.log"
    with log.open("w") as handle:
        process = subprocess.Popen([sys.executable, "-c", code, str(batch_repo), *arguments(batch_repo)],
                                   stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while not (batch_repo / "ready.json").exists():
                assert process.poll() is None, log.read_text()
                assert time.monotonic() < deadline, log.read_text()
                time.sleep(0.05)
            pids = read(batch_repo / "ready.json")
            process.send_signal(sig)
            assert process.wait(timeout=15) == 130, log.read_text()
            assert not alive(pids["child"])
            assert not alive(pids["grandchild"])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    root = batch_repo / "evidence"
    assert read(root / "state/batch-run.json")["status"] == "cancelled"
    assert read(root / "state/batch-run-sample-b.json")["status"] == "cancelled"
    assert (root / "runs/batch-run-sample-a/SUCCESS.json").is_file()
    assert (root / ".staging/batch-run/samples/sample-a").is_dir()
    assert not (root / "runs/batch-run").exists()


def test_cancellation_during_popen_registration_reaps_process():
    runner = ProcessRunner(dict(os.environ))
    popen = subprocess.Popen
    processes = []

    def cancel_after_spawn(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        runner.cancelled = True
        return process

    with patch("genein.pipeline.sample.subprocess.Popen", side_effect=cancel_after_spawn):
        with pytest.raises(BatchCancelled):
            runner.run([sys.executable, "-c", "import time; time.sleep(60)"])
    assert processes[0].poll() is not None


def test_cancellation_before_spawn_runs_nothing():
    runner = ProcessRunner(dict(os.environ))
    runner.cancelled = True
    with patch("genein.pipeline.sample.subprocess.Popen") as popen:
        with pytest.raises(BatchCancelled):
            runner.run(["false"])
        popen.assert_not_called()


@pytest.mark.parametrize("during_commit", [False, True])
def test_cancellation_at_finalization_boundary_has_no_partial_commit(batch_repo, during_commit, monkeypatch):
    import io
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from dashboard import jobs
    from evidence_dashboard import EvidenceDashboardService

    service = EvidenceDashboardService(batch_repo)
    service.evidence_root = batch_repo / "evidence"
    monkeypatch.setattr(jobs, "get_evidence_service", lambda: service)
    monkeypatch.setattr(jobs, "LOG_DIR", batch_repo)
    monkeypatch.setattr(jobs, "jobs", {
        "batch-run": {"status": "queued", "action": "evidence_batch", "output": []},
    })
    monkeypatch.setattr(jobs, "build_command", lambda *_: (["controlled-batch"], {}))
    process = SimpleNamespace(stdout=io.StringIO(""), returncode=None)

    def wait_for_batch():
        # Only the dashboard's Popen boundary is adapted. The batch, its helper
        # subprocesses, transaction and signal handlers all execute for real.
        process.returncode = main(arguments(batch_repo), repo_root=batch_repo)
        return process.returncode

    process.wait = wait_for_batch
    monkeypatch.setattr(jobs, "Popen", lambda *_args, **_kwargs: process)
    run = ProcessRunner.run
    cancellation_sent = False

    def request_cancellation():
        nonlocal cancellation_sent
        if cancellation_sent:
            return
        cancellation_sent = True
        assert jobs.request_job_cancellation("batch-run")["ok"]
        os.kill(os.getpid(), signal.SIGTERM)

    def cancel_at_boundary(self, command, **kwargs):
        args = [str(arg) for arg in command]
        if during_commit and Path(args[1]).name == "finalize_batch.py":
            # Deliver a real signal while the commit command is entering the
            # non-interruptible transaction, as bash previously deferred traps.
            request_cancellation()
        result = run(self, command, **kwargs)
        # Stage/status transitions run in-process now (no subprocess boundary
        # to spy on), so the last remaining subprocess before the commit --
        # summarize_batch.py, which runs right before the report_export stage
        # and the pre-commit checkpoint -- is the closest equivalent hook.
        if not during_commit and Path(args[1]).name == "summarize_batch.py":
            request_cancellation()
        return result

    with patch.object(ProcessRunner, "run", cancel_at_boundary):
        jobs.run_job("batch-run", "evidence_batch", {"run_id": "batch-run"})
    assert jobs.jobs["batch-run"]["exit_code"] == 130
    assert jobs.jobs["batch-run"]["status"] == ("done" if during_commit else "cancelled")
    assert jobs.jobs["batch-run"]["evidence_v2_status"] == ("done" if during_commit else "cancelled")
    root = batch_repo / "evidence"
    if during_commit:
        assert read(root / "runs/batch-run/SUCCESS.json")["sample_count"] == 2
        assert read(root / "state/batch-run.json")["status"] == "done"
        assert not (root / ".staging/batch-run").exists()
    else:
        assert not (root / "runs/batch-run").exists()
        assert read(root / "state/batch-run.json")["status"] == "cancelled"


def test_failed_process_also_terminates_its_surviving_tools(tmp_path):
    ready = tmp_path / "tool.pid"
    code = ("import subprocess,sys; from pathlib import Path; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "Path(sys.argv[1]).write_text(str(p.pid)); sys.exit(23)")
    runner = ProcessRunner(dict(os.environ))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.run([sys.executable, "-c", code, str(ready)])
    assert failure.value.returncode == 23
    assert not alive(int(ready.read_text()))


def test_public_and_private_sample_boundaries_share_config_and_stages(tmp_path):
    repo = tmp_path / "shell repo"
    pipeline = repo / "scripts/pipeline"
    pipeline.mkdir(parents=True)
    (repo / "scripts/lib").symlink_to(ROOT / "scripts/lib", target_is_directory=True)
    (repo / "config").mkdir()
    (repo / "config/picornavirus.env").write_text("THREADS=6\nASSEMBLER=velvet\n")
    for name in ("run.sh", "run_sample.sh", "prepare_run.sh"):
        shutil.copyfile(ROOT / "scripts/pipeline" / name, pipeline / name)
    for name in ("resolve_config.py", "analysis_profiles.py"):
        (pipeline / name).symlink_to(ROOT / "scripts/pipeline" / name)
    # Execute real setup + resolver, then stop before any scientific-tool stages.
    steps = (ROOT / "scripts/pipeline/sample_steps.sh").read_text()
    (pipeline / "sample_steps.sh").write_text(steps[:steps.index('if [[ $SKIP_ASSEMBLY')] +
                                              '\ncat "$RESOLVED_CONFIG_JSON"\n')
    env = dict(os.environ, THREADS="8", ASSEMBLER="spades", ANALYSIS_PROFILES_CONFIG=str(ROOT / "config/analysis_profiles.json"))
    values = []
    for entry in ("run.sh", "run_sample.sh"):
        result = subprocess.run(["bash", pipeline / entry, "--sample", "sample-a", "--threads", "2"],
                                env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        values.append(json.loads(result.stdout))
    assert values[0] == values[1]
    assert values[0]["threads"] == 2
    assert values[0]["assembler"] == "spades"
    assert values[0]["evidence"]["v2"] is False
    result = subprocess.run(["bash", pipeline / "run_sample.sh", "--batch-manifest", "ignored.tsv"],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert "does not accept batches" in result.stderr
    # The public dispatcher retains its pre-resolver batch defaults/overrides.
    (pipeline / "run_batch.py").write_text("import json,sys; print(json.dumps(sys.argv[1:]))\n")
    result = subprocess.run(["bash", pipeline / "run.sh", "--batch-manifest", "manifest.tsv",
                             "--evidence-profiles", "catalog.json", "--evidence-root", "outputs"],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["--batch-manifest", "manifest.tsv", "--profiles", "catalog.json",
                                         "--evidence-root", "outputs", "--threads", "6"]


def test_checkout_adapter_ignores_foreign_pythonpath(tmp_path):
    foreign = tmp_path / "genein"
    foreign.mkdir()
    (foreign / "__init__.py").write_text('raise RuntimeError("wrong checkout")\n')
    result = subprocess.run(["bash", ROOT / "scripts/evidence/run_batch.sh", "--help"],
                            env=dict(os.environ, PYTHONPATH=str(tmp_path)), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Internal Evidence batch orchestrator" in result.stdout
