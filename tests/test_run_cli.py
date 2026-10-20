"""Coverage for `genein run` (src/genein/pipeline/cli.py): input validation,
external-output isolation (including paths with spaces), env/receipt wiring
and exit-code propagation. Uses a stub run_sample.sh so no real
bioinformatics tools are required; the CLI's own logic is what is exercised.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pytest

from genein.pipeline import cli as pipeline_cli

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "posix", reason="genein run requires Linux/WSL")


def build_args(**overrides):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline_cli.register_commands(commands)
    argv = ["run"]
    for key, value in overrides.items():
        flag = "--" + key.replace("_", "-")
        if value is True:
            argv.append(flag)
        elif value is not None:
            argv += [flag, str(value)]
    return parser.parse_args(argv)


@pytest.fixture
def cli_repo(tmp_path, monkeypatch):
    repo = tmp_path / "source with spaces"
    (repo / "scripts/pipeline").mkdir(parents=True)
    for name in ("evidence", "lib"):
        (repo / "scripts" / name).symlink_to(ROOT / "scripts" / name, target_is_directory=True)
    (repo / "config").symlink_to(ROOT / "config", target_is_directory=True)
    (repo / "scripts/pipeline/run_sample.sh").write_text(
        f'#!/usr/bin/env bash\nexec python3 "{ROOT}/scripts/tests/fixtures/run_cli_child.py" "$@"\n'
    )
    monkeypatch.setenv("GENEIN_REPO_ROOT", str(repo))
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    return repo


def blast_db(tmp_path):
    db = tmp_path / "panel"
    Path(str(db) + ".db-manifest.json").write_text("{}", encoding="utf-8")
    return db


def fastq(tmp_path, name):
    path = tmp_path / name
    path.write_text("@r\nACGT\n+\nIIII\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Input validation (prepare() must fail before touching disk or a process)
# ---------------------------------------------------------------------------

def test_r1_without_r2_is_rejected(cli_repo, tmp_path):
    args = build_args(r1=fastq(tmp_path, "r1.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1")
    with pytest.raises(ValueError, match="--r1 and --r2"):
        pipeline_cli.prepare(args, cli_repo)


def test_sample_without_any_input_is_rejected(cli_repo, tmp_path):
    args = build_args(output_root=tmp_path / "out", blast_db=blast_db(tmp_path), sample="s1")
    with pytest.raises(ValueError, match="requires --r1/--r2"):
        pipeline_cli.prepare(args, cli_repo)


def test_positive_control_without_expected_target_is_rejected(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1", role="positive")
    with pytest.raises(ValueError, match="Controle positivo exige um alvo esperado"):
        pipeline_cli.prepare(args, cli_repo)


def test_assembly_consensus_rejects_explicit_assembler(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1",
                       analysis_profile="assembly-consensus", assembler="spades")
    with pytest.raises(ValueError, match="cannot be combined"):
        pipeline_cli.prepare(args, cli_repo)


def test_output_root_inside_source_tree_is_rejected(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=cli_repo / "inside",
                       blast_db=blast_db(tmp_path), sample="s1")
    with pytest.raises(ValueError, match="outside the Gene-In source tree"):
        pipeline_cli.prepare(args, cli_repo)


def test_existing_output_root_is_never_overwritten(cli_repo, tmp_path):
    existing = tmp_path / "out"
    existing.mkdir()
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=existing,
                       blast_db=blast_db(tmp_path), sample="s1")
    with pytest.raises(ValueError, match="already exists"):
        pipeline_cli.prepare(args, cli_repo)


def test_missing_blast_db_manifest_is_rejected(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=tmp_path / "no-such-panel", sample="s1")
    with pytest.raises(ValueError, match="Banco BLAST sem manifesto preparado"):
        pipeline_cli.prepare(args, cli_repo)


def test_batch_manifest_rejects_sample_metadata(cli_repo, tmp_path):
    manifest = tmp_path / "batch.tsv"
    manifest.write_text("batch_id\tsample_id\n", encoding="utf-8")
    args = build_args(batch_manifest=manifest, output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), role="positive")
    with pytest.raises(ValueError, match="Batch inputs and sample metadata"):
        pipeline_cli.prepare(args, cli_repo)


def test_batch_manifest_rejects_skip_qc(cli_repo, tmp_path):
    manifest = tmp_path / "batch.tsv"
    manifest.write_text("batch_id\tsample_id\n", encoding="utf-8")
    args = build_args(batch_manifest=manifest, output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), skip_qc=True)
    with pytest.raises(ValueError, match="only supported for single samples"):
        pipeline_cli.prepare(args, cli_repo)


# ---------------------------------------------------------------------------
# End-to-end wiring: env vars, receipt, exit-code propagation, spaced paths
# ---------------------------------------------------------------------------

def test_successful_run_writes_receipt_and_propagates_env(cli_repo, tmp_path, monkeypatch):
    monkeypatch.delenv("GENEIN_TEST_EXIT", raising=False)
    output_root = tmp_path / "external output with spaces"
    marker = tmp_path / "marker.json"
    monkeypatch.setenv("GENEIN_TEST_MARKER", str(marker))
    db = blast_db(tmp_path)
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=output_root, blast_db=db,
                       sample="sample-1", threads=2, role="positive", expected_target="target-x")
    code = pipeline_cli.run(args)
    assert code == 0

    receipt = json.loads((output_root / "execution.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["exit_code"] == 0
    assert receipt["software_version"] == "2.0.1"
    assert receipt["source_commit"]
    assert receipt["output_root"] == str(output_root)
    assert receipt["source_root"] == str(cli_repo)
    assert not (cli_repo / "results").exists()
    assert not (cli_repo / "data").exists()

    record = json.loads(marker.read_text(encoding="utf-8"))
    assert record["env"]["GENEIN_WORK_ROOT"] == str(output_root)
    assert record["env"]["BLAST_DB"] == str(db)
    assert record["env"]["EVIDENCE_ROLE"] == "positive"
    assert record["env"]["EVIDENCE_EXPECTED_TARGET"] == "target-x"
    assert record["env"]["EVIDENCE_RUN_ID"]


def test_prepare_keeps_the_user_config_when_the_output_replaces_the_work_root(cli_repo, tmp_path, monkeypatch):
    work = tmp_path / "user-work"
    work.mkdir()
    monkeypatch.setenv("GENEIN_WORK_ROOT", str(work))
    monkeypatch.delenv("GENEIN_CONFIG_FILE", raising=False)
    output = tmp_path / "external output"
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=output,
                      blast_db=blast_db(tmp_path), sample="sample-1")
    _output, _command, env, _run_id = pipeline_cli.prepare(args, cli_repo)
    assert env["GENEIN_WORK_ROOT"] == str(output.resolve())
    assert env["GENEIN_CONFIG_FILE"] == str(work / "config" / "picornavirus.env")
    assert not env["GENEIN_CONFIG_FILE"].startswith(str(cli_repo))


def test_host_expected_public_option_is_forwarded_to_filter_environment(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "host-expected-run",
                      blast_db=blast_db(tmp_path), sample="sample-1", host_expected="false")
    _output, _command, env, _run_id = pipeline_cli.prepare(args, cli_repo)
    assert env["HOST_EXPECTED"] == "false"


def test_host_expected_public_option_rejects_values_outside_true_false(tmp_path):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline_cli.register_commands(commands)
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--host-expected", "maybe"])


def test_failed_child_process_sets_receipt_failed_and_propagates_exit_code(cli_repo, tmp_path, monkeypatch):
    output_root = tmp_path / "out"
    marker = tmp_path / "marker.json"
    monkeypatch.setenv("GENEIN_TEST_MARKER", str(marker))
    monkeypatch.setenv("GENEIN_TEST_EXIT", "3")
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=output_root,
                       blast_db=blast_db(tmp_path), sample="sample-1")
    code = pipeline_cli.run(args)
    assert code == 3
    receipt = json.loads((output_root / "execution.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["exit_code"] == 3


def test_batch_manifest_command_forwards_sample_options(cli_repo, tmp_path):
    manifest = tmp_path / "batch.tsv"
    manifest.write_text("batch_id\tsample_id\n", encoding="utf-8")
    args = build_args(batch_manifest=manifest, output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), assembler="spades", threads=2)
    _output, command, _env, _run_id = pipeline_cli.prepare(args, cli_repo)
    assert command[:2] == [sys.executable, str(cli_repo / "scripts/pipeline/run_batch.py")]
    assert "--sample-arg=--assembler" in command
    assert "--sample-arg=spades" in command
    assert "--threads" in command and "2" in command


def test_killed_child_receipt_matches_dashboard_classification(cli_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GENEIN_TEST_MARKER", str(tmp_path / "marker.json"))
    monkeypatch.setenv("GENEIN_TEST_EXIT", "1")
    monkeypatch.setenv("GENEIN_TEST_LOG", "subprocess.CalledProcessError: blastn died with <Signals.SIGKILL: 9>\n")
    output = tmp_path / "out"
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=output, blast_db=blast_db(tmp_path), sample="s1")
    assert pipeline_cli.run(args) == 1
    receipt = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert receipt["failure_type"] == "PROCESS_KILLED"
    assert "SIGKILL" in receipt["failure_message"]


def test_signal_exit_receipt_is_process_killed(cli_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GENEIN_TEST_MARKER", str(tmp_path / "marker.json"))
    monkeypatch.setenv("GENEIN_TEST_EXIT", "137")
    output = tmp_path / "out"
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=output, blast_db=blast_db(tmp_path), sample="s1")
    assert pipeline_cli.run(args) == 137
    receipt = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert receipt["failure_type"] == "PROCESS_KILLED"


def test_oom_trace_receipt_is_memory_exhausted(cli_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GENEIN_TEST_MARKER", str(tmp_path / "marker.json"))
    monkeypatch.setenv("GENEIN_TEST_EXIT", "1")
    monkeypatch.setenv("GENEIN_TEST_LOG", "terminate called after throwing an instance of 'std::bad_alloc'\n")
    output = tmp_path / "out"
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=output, blast_db=blast_db(tmp_path), sample="s1")
    assert pipeline_cli.run(args) == 1
    receipt = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert receipt["failure_type"] == "MEMORY_EXHAUSTED"


def test_database_failure_receipt_is_typed(cli_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GENEIN_TEST_MARKER", str(tmp_path / "marker.json"))
    monkeypatch.setenv("GENEIN_TEST_EXIT", "65")
    output = tmp_path / "out"
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=output, blast_db=blast_db(tmp_path), sample="s1")
    assert pipeline_cli.run(args) == 65
    receipt = json.loads((output / "execution.json").read_text())
    assert receipt["failure_type"] == "INPUT_INVALID"
    assert receipt["failed_stage"] == "database_preflight"


def test_source_root_requires_pipeline_adapters(tmp_path, monkeypatch):
    monkeypatch.setenv("GENEIN_REPO_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="Pipeline adapters are missing"):
        pipeline_cli.source_root()


def test_runtime_environment_matches_launcher(cli_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GENEIN_ENV_DIR", "/wrong/old/environment")
    args = build_args(single=fastq(tmp_path, "input.fq"), output_root=tmp_path / "run",
                      blast_db=blast_db(tmp_path), sample="s1")
    _, _, env, _ = pipeline_cli.prepare(args, cli_repo)
    assert env["GENEIN_ENV_DIR"] == str(Path(sys.executable).parent.parent)
    assert env["PATH"].split(os.pathsep)[0] == str(Path(sys.executable).parent)


def bowtie2_index(tmp_path, name="host_bt2", extension="bt2"):
    prefix = tmp_path / name
    for part in ("1", "2", "3", "4", "rev.1", "rev.2"):
        Path(f"{prefix}.{part}.{extension}").write_text("x", encoding="utf-8")
    return prefix


def test_host_index_requires_host_name(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1",
                       host_index=bowtie2_index(tmp_path))
    with pytest.raises(ValueError, match="requires --host-name"):
        pipeline_cli.prepare(args, cli_repo)


def test_host_index_is_never_silently_skipped(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1", host_name="Sus scrofa",
                       host_index=bowtie2_index(tmp_path), skip_host_filter=True)
    with pytest.raises(ValueError, match="do not combine it with --skip-host-filter"):
        pipeline_cli.prepare(args, cli_repo)


def test_incomplete_host_index_is_rejected_before_reserving_output(cli_repo, tmp_path):
    prefix = bowtie2_index(tmp_path)
    Path(f"{prefix}.rev.2.bt2").unlink()
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1",
                       host_name="Sus scrofa", host_index=prefix)
    with pytest.raises(ValueError, match="Bowtie2 host index not found"):
        pipeline_cli.prepare(args, cli_repo)
    assert not (tmp_path / "out").exists()


def test_declared_host_without_index_is_rejected(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1", host_name="Sus scrofa")
    with pytest.raises(ValueError, match="only runs with --host-index"):
        pipeline_cli.prepare(args, cli_repo)


def test_large_host_index_enables_filtering(cli_repo, tmp_path):
    args = build_args(single=fastq(tmp_path, "se.fq"), output_root=tmp_path / "out",
                       blast_db=blast_db(tmp_path), sample="s1", host_name="Sus scrofa",
                       host_index=bowtie2_index(tmp_path, "large_bt2", "bt2l"))
    _, _, env, _ = pipeline_cli.prepare(args, cli_repo)
    assert env["HOST_FILTER_ENABLED"] == "true"
    assert env["HOST_NAME"] == "Sus scrofa"
