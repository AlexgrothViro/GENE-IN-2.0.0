import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dashboard import handler, jobs
from promote_blast_database import promote, promotion_lock
from verify_blast_database_manifest import verify


ROOT = Path(__file__).resolve().parents[2]
COLLECTION = "nucleotide"


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def prepared_database(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("GENEIN_WORK_ROOT", str(tmp_path))
    monkeypatch.setenv("GENEIN_CONFIG_FILE", str(tmp_path / "config/fixture.env"))
    monkeypatch.delenv("BLAST_DB", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/analysis_profiles.json").write_bytes((ROOT / "config/analysis_profiles.json").read_bytes())
    prefix = tmp_path / "blastdb/custom"
    storage = hashlib.sha256(prefix.name.encode()).hexdigest()
    generation = prefix.parent / f".{storage}.generations/fixture-generation"
    generation.mkdir(parents=True)
    component = generation / "database.nsq"
    component.write_bytes(b"synthetic index identity fixture")
    alias = prefix.with_suffix(".nal")
    alias.write_text(f'DBLIST "{(generation / "database").relative_to(prefix.parent)}"\n', encoding="utf-8")
    manifest = prefix.with_suffix(".db-manifest.json")
    write_json(manifest, {
        "schema_version": "1.0", "logical_prefix": str(prefix), "generation_id": generation.name,
        "index_basename": "database", "created_at": "2026-01-01T00:00:00+00:00",
        "query_source": {"query": "fixture-A", "ncbi_db": COLLECTION},
        "source_fasta": {"path": "fixture-reference", "size": 10, "sha256": "a" * 64},
        "produced_files": {component.name: {"size": component.stat().st_size, "sha256": hashlib.sha256(component.read_bytes()).hexdigest()}},
    })
    monkeypatch.setattr(jobs.get_evidence_service(), "manifest_export", lambda _identifier: tmp_path / "fixture.tsv")
    return prefix, alias, manifest


@pytest.mark.parametrize("action", ["pipeline", "evidence_pipeline", "evidence_batch"])
def test_custom_jobs_bind_query_to_the_selected_index(prepared_database, action):
    prefix, _, manifest = prepared_database
    params = {"sample": "sample", "manifest_id": "fixture", "db": "custom", "db_query": "fixture-A"}
    _, env = jobs.build_command(action, params)
    assert env["BLAST_DB"] == str(prefix)
    assert env["DB_QUERY"] == "fixture-A"
    assert env["NCBI_DB"] == COLLECTION
    assert env["GENEIN_EXPECTED_BLAST_MANIFEST_SHA256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="difere da registrada"):
        jobs.build_command(action, dict(params, db_query="fixture-B"))
    with pytest.raises(ValueError, match="difere da registrada"):
        jobs.build_command(action, dict(params, ncbi_db="other-fixture"))


def test_missing_explicit_query_uses_selected_manifest_and_ignores_stale_default(prepared_database, tmp_path, monkeypatch):
    prefix, _, _ = prepared_database
    monkeypatch.setenv("NCBI_DB", "stale-default")
    other = tmp_path / "elsewhere/custom"
    other.parent.mkdir()
    (other.with_suffix(".db-manifest.json")).write_text("{}", encoding="utf-8")
    _, env = jobs.build_command("pipeline", {"sample": "sample", "db": "custom"})
    assert (env["DB_QUERY"], env["NCBI_DB"]) == ("fixture-A", COLLECTION)
    monkeypatch.setenv("BLAST_DB", str(other))
    with pytest.raises(ValueError, match="consulta do índice customizado não pôde ser confirmada"):
        jobs.build_command("pipeline", {"sample": "sample", "db": "custom", "db_query": "fixture-A"})
    assert prefix.is_absolute()


def test_preparation_targets_the_same_prefix_as_analysis(prepared_database, tmp_path, monkeypatch):
    prefix, _, _ = prepared_database
    params = {"sample": "sample", "db": "custom", "db_query": "fixture-A", "ncbi_db": COLLECTION}
    _, preparation = jobs.build_command("build_db", params)
    _, analysis = jobs.build_command("pipeline", params)
    assert preparation["BLAST_DB"] == analysis["BLAST_DB"] == str(prefix)
    assert preparation["NCBI_DB"] == analysis["NCBI_DB"] == COLLECTION

    overridden = tmp_path / "alternate/custom"
    monkeypatch.setenv("BLAST_DB", str(overridden))
    _, preparation = jobs.build_command("build_db", params)
    assert preparation["BLAST_DB"] == str(overridden)


@pytest.mark.parametrize("case", ["valid", "stale", "different_reference", "different_index"])
def test_legacy_query_requires_a_receipt_for_the_selected_generation(prepared_database, tmp_path, case):
    prefix, _, manifest = prepared_database
    generation = json.loads(manifest.read_text())
    generation.pop("query_source")
    write_json(manifest, generation)
    receipt = prefix.with_suffix(".index-manifest.json")
    reference = dict(generation["source_fasta"])
    if case == "different_reference":
        reference["sha256"] = "b" * 64
    write_json(receipt, {"reference": reference})
    metadata = tmp_path / "db/custom/metadata.json"
    metadata.parent.mkdir(parents=True)
    write_json(metadata, {
        "db": "custom", "db_query": "fixture-A", "ncbi_db": COLLECTION,
        "index_manifest": str(receipt if case != "different_index" else receipt.with_name("other.json")),
        "updated_at": "2025-12-31T00:00:00+00:00" if case == "stale" else "2026-01-02T00:00:00+00:00",
    })
    params = {"sample": "sample", "db": "custom"}
    if case == "valid":
        _, env = jobs.build_command("pipeline", params)
        assert env["DB_QUERY"] == "fixture-A"
        with pytest.raises(ValueError, match="difere da registrada"):
            jobs.build_command("pipeline", dict(params, db_query="fixture-B"))
    else:
        with pytest.raises(ValueError, match="não pôde ser confirmada"):
            jobs.build_command("pipeline", params)


def test_alias_and_manifest_swaps_are_rejected(prepared_database):
    prefix, alias, manifest = prepared_database
    _, env = jobs.build_command("pipeline", {"sample": "sample", "db": "custom"})
    write_json(manifest, dict(json.loads(manifest.read_text()), changing_generation=True))
    with pytest.raises(ValueError, match="mudou desde a seleção"):
        verify(prefix, expected_sha256=env["GENEIN_EXPECTED_BLAST_MANIFEST_SHA256"])
    alias.write_text("DBLIST other-database\n", encoding="utf-8")
    with pytest.raises(ValueError, match="não pôde ser confirmada"):
        jobs.build_command("evidence_pipeline", {"sample": "sample", "db": "custom"})


def test_mismatch_is_rejected_before_admission(prepared_database, monkeypatch):
    pending = {}
    monkeypatch.setattr(handler, "jobs", pending)
    request = object.__new__(handler.DashboardHandler)
    with pytest.raises(ValueError, match="difere da registrada"):
        request.start_job("evidence_pipeline", {"sample": "sample", "db": "custom", "db_query": "fixture-B"})
    assert pending == {}


def test_admission_captures_implicit_query_and_generation(prepared_database, monkeypatch):
    import threading

    _, _, manifest = prepared_database
    registered = {}
    starts = []
    monkeypatch.setattr(handler, "jobs", registered)
    monkeypatch.setattr(handler, "json_response", lambda _request, _code, payload: payload)
    monkeypatch.setattr(threading, "Thread", lambda **task: SimpleNamespace(start=lambda: starts.append(task["args"])))
    request = object.__new__(handler.DashboardHandler)
    job_id = request.start_job("pipeline", {"sample": "sample", "db": "custom"})["job_id"]
    assert registered[job_id]["database_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert len(starts) == 1
    assert starts[0][2]["db_query"] == "fixture-A"
    assert starts[0][2]["ncbi_db"] == COLLECTION


def test_worker_rejects_a_generation_replaced_while_queued(prepared_database, monkeypatch):
    prefix, _, _ = prepared_database
    job_id = "2" * 32
    queued = {"status": "queued", "database_manifest_sha256": "f" * 64}
    monkeypatch.setattr(jobs, "jobs", {job_id: queued})
    monkeypatch.setattr(jobs, "launch_claimed_job", lambda *args: pytest.fail("stale job launched"))
    jobs.run_job(job_id, "pipeline", {"sample": "sample", "db": "custom", "db_query": "fixture-A"})
    assert queued["status"] == "failed"
    assert "mudou depois da seleção" in queued["failure_message"]
    with promotion_lock(prefix, nonblocking=True):
        pass


def test_worker_leases_the_database_until_it_stops_using_it(prepared_database, monkeypatch):
    prefix, _, _ = prepared_database
    job_id = "1" * 32
    monkeypatch.setattr(jobs, "jobs", {job_id: {"status": "queued"}})
    launches = []

    def launch(_job_id, command, env):
        launches.append(command)
        assert env["BLAST_DB"] == str(prefix)
        with promotion_lock(prefix, shared=True, nonblocking=True):
            with pytest.raises(BlockingIOError):
                with promotion_lock(prefix, nonblocking=True):
                    pytest.fail("the alias can be overwritten while a job is using it")
        return None

    monkeypatch.setattr(jobs, "launch_claimed_job", launch)
    jobs.run_job(job_id, "pipeline", {"sample": "sample", "db": "custom"})
    assert len(launches) == 1
    with promotion_lock(prefix, nonblocking=True):
        pass


def test_promotion_records_the_query_in_the_generation(monkeypatch, tmp_path):
    import promote_blast_database as publisher

    stage = tmp_path / "staging"
    stage.mkdir()
    (stage / "database.nsq").write_bytes(b"synthetic index")
    source = tmp_path / "input.fixture"
    source.write_bytes(b"reference identity only")
    prefix = tmp_path / "custom"
    manifest = prefix.with_suffix(".db-manifest.json")

    def local_commands(command, _description, cwd=None):
        if command[0] == "fake-alias-tool":
            (cwd / (command[command.index("-out") + 1] + ".nal")).write_text(
                'DBLIST "' + command[command.index("-dblist") + 1] + '"\n', encoding="utf-8",
            )

    monkeypatch.setattr(publisher, "run_checked", local_commands)
    result = promote(stage, prefix, source, "fake-db-tool", "fake-alias-tool", manifest, build_name="database",
                     query_source={"query": "fixture-A", "ncbi_db": COLLECTION})
    assert json.loads(manifest.read_text())["query_source"] == {"query": "fixture-A", "ncbi_db": COLLECTION}
    assert result["query_source"] == json.loads(manifest.read_text())["query_source"]
