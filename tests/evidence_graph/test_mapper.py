from __future__ import annotations

import json
from pathlib import Path

import pytest

from genein.evidence_graph.graph_builder.mapper import map_all
from genein.evidence_graph.graph_builder.parse import digest_ref, node_id, parse_interval_list, sha256_file
from genein.evidence_graph.graph_builder.pipeline import build
from genein.evidence_graph.graph_builder.reader import read, verify_promotion
from genein.evidence_graph.graph_builder.types import BuildRequest
from genein.evidence_graph.graph_builder.writer import DestinationExistsError, StagingConflictError, write
from tests.evidence_graph.mapper_fixtures import ALPHA2, FIXTURES_ROOT, PRODUCTION_CATALOG, materialize_run

CATALOG = PRODUCTION_CATALOG


def _request(run_dir: Path, output_root: Path) -> BuildRequest:
    return BuildRequest(
        run_dir=run_dir,
        output_root=output_root,
        rule_catalog_path=CATALOG,
    )


def test_parse_interval_list_normalizes_gapped_locus():
    intervals = parse_interval_list("100-220;350-400")
    assert intervals == [{"start": 100, "end": 220}, {"start": 350, "end": 400}]


def test_parse_interval_list_rejects_inverted():
    assert parse_interval_list("400-100") == []


def test_parse_interval_list_strict_no_partial():
    assert parse_interval_list("100-220;bad;350-400") == []


def test_parse_interval_list_rejects_comma_separator():
    assert parse_interval_list("100-220,350-400") == []


def test_node_id_collision_resistant():
    left = node_id("HSP", "a" * 40)
    right = node_id("HSP", "a" * 39 + "b")
    assert left != right
    assert left.startswith("HSP-")
    assert len(left.split("-")[-1]) == 12


def test_digest_ref_fails_missing_and_malformed():
    with pytest.raises(ValueError, match="ausente"):
        digest_ref({}, "missing.tsv")
    with pytest.raises(ValueError, match="malformado"):
        digest_ref({"x.tsv": {"sha256": "deadbeef"}}, "x.tsv")


def test_reader_alpha2_promoted(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "alpha2"))
    assert errors == []
    source = read(_request(run_dir, tmp_path / "output" / "alpha2"))
    assert source.run_id == "fixture-alpha2-run"


def _rewrite_manifest(run_dir: Path, manifest: dict) -> None:
    (run_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    success = json.loads((run_dir / "SUCCESS.json").read_text(encoding="utf-8"))
    success["artifact_count"] = len(manifest.get("files", {}))
    success["artifact_manifest_sha256"] = sha256_file(run_dir / "artifact_manifest.json")
    (run_dir / "SUCCESS.json").write_text(json.dumps(success, indent=2) + "\n", encoding="utf-8")


def test_reader_digest_mismatch(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    key = next(iter(manifest["files"]))
    manifest["files"][key]["sha256"] = "0" * 64
    _rewrite_manifest(run_dir, manifest)
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "digest"))
    assert any("digest divergente" in err for err in errors)


def test_reader_size_mismatch(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    key = next(iter(manifest["files"]))
    manifest["files"][key]["size"] = 1
    _rewrite_manifest(run_dir, manifest)
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "size"))
    assert any("tamanho divergente" in err for err in errors)


def test_reader_path_traversal(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["../outside.tsv"] = {"sha256": "0" * 64, "size": 0}
    _rewrite_manifest(run_dir, manifest)
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "trav"))
    assert any("path traversal" in err or "escapa" in err for err in errors)


def test_reader_optional_not_autoload(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    # Non-contract undeclared file must not be auto-loaded.
    (run_dir / "notes.txt").write_text("ignore\n", encoding="utf-8")
    source = read(_request(run_dir, tmp_path / "output" / "opt"))
    assert "notes.txt" not in source.tables
    assert "hsp_evidence.tsv" not in source.tables


def test_reader_undeclared_contract_artifact(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    (run_dir / "hsp_evidence.tsv").write_text("hsp_id\n", encoding="utf-8")
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "undeclared"))
    assert any("não declarado" in err for err in errors)


def test_reader_incomplete_022_contract(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    (run_dir / "template_lineage.tsv").unlink()
    from tests.evidence_graph.mapper_fixtures import write_manifest, write_success
    write_manifest(run_dir)
    write_success(run_dir, base={"mapper_source_version": "0.2.2"})
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "incomplete"))
    assert any("contrato 0.2.2 incompleto" in err for err in errors)


def test_reader_bad_status(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    success = json.loads((run_dir / "SUCCESS.json").read_text(encoding="utf-8"))
    success["status"] = "failed"
    (run_dir / "SUCCESS.json").write_text(json.dumps(success), encoding="utf-8")
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "bad-status"))
    assert any("SUCCESS.status inválido" in err for err in errors)


def test_reader_foreign_run_id(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    sample = json.loads((run_dir / "sample_evidence.json").read_text(encoding="utf-8"))
    sample["run_id"] = "foreign-run"
    (run_dir / "sample_evidence.json").write_text(json.dumps(sample), encoding="utf-8")
    from tests.evidence_graph.mapper_fixtures import write_manifest, write_success
    write_manifest(run_dir)
    # Keep SUCCESS.run_id as original fixture-alpha2-run
    success = json.loads((run_dir / "SUCCESS.json").read_text(encoding="utf-8"))
    write_success(run_dir, base={**success, "run_id": "fixture-alpha2-run"})
    # write_success overwrites run_id from sample — force SUCCESS foreign mismatch
    success = json.loads((run_dir / "SUCCESS.json").read_text(encoding="utf-8"))
    success["run_id"] = "fixture-alpha2-run"
    success["artifact_manifest_sha256"] = sha256_file(run_dir / "artifact_manifest.json")
    (run_dir / "SUCCESS.json").write_text(json.dumps(success), encoding="utf-8")
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "foreign"))
    assert any("run_id estrangeiro" in err for err in errors)


def test_reader_artifact_count_mismatch(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    success = json.loads((run_dir / "SUCCESS.json").read_text(encoding="utf-8"))
    success["artifact_count"] = 1
    (run_dir / "SUCCESS.json").write_text(json.dumps(success), encoding="utf-8")
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "count"))
    assert any("artifact_count diverge" in err for err in errors)


def test_reader_missing_size_rejected(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    key = next(iter(manifest["files"]))
    del manifest["files"][key]["size"]
    _rewrite_manifest(run_dir, manifest)
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "nosize"))
    assert any("tamanho ausente" in err for err in errors)


def test_reader_tampered_success(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    (run_dir / "SUCCESS.json").write_text("{not-json", encoding="utf-8")
    errors = verify_promotion(_request(run_dir, tmp_path / "output" / "tampered"))
    assert errors


def test_mapper_no_hsp_abstains(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "no-hsp"))
    output = map_all(source)
    assert not any(node["type"] == "HSP" for node in output.nodes)
    assert any("P-E5-1" in note for note in output.scope_notes)
    assert output.hsp_evidence_rows == []


def test_mapper_complete_with_hsp(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "complete"))
    output = map_all(source)
    hsps = [node for node in output.nodes if node["type"] == "HSP"]
    assert len(hsps) == 2
    assert all(node["observation"]["eligible"] is True for node in hsps)
    assert len(output.hsp_evidence_rows) == 2
    loci = [node for node in output.nodes if node["type"] == "Locus"]
    assert len(loci) == 1
    assert isinstance(loci[0]["interval"], list)
    assert len(loci[0]["interval"]) == 2


def test_mapper_no_placeholders(tmp_path):
    run_dir = materialize_run("missing_fields", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "placeholders"))
    output = map_all(source)
    hsp = next(node for node in output.nodes if node["type"] == "HSP")
    assert hsp["matches"] is None
    assert hsp["mismatches"] is None
    assert hsp["gaps"] is None
    assert hsp["coord_system"] is None
    for node in output.nodes:
        blob = json.dumps(node, ensure_ascii=False)
        assert "ABSTAINED:" not in blob


def test_mapper_missing_fields_marks_ineligible(tmp_path):
    run_dir = materialize_run("missing_fields", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "missing"))
    output = map_all(source)
    hsp = next(node for node in output.nodes if node["type"] == "HSP")
    assert hsp["observation"]["eligible"] is False
    assert hsp["observation"]["status"] == "NOT_EVALUABLE"
    assert "matches" in hsp["observation"]["missing_fields"]
    assert hsp["coord_system"] is None
    assert hsp["matches"] is None


def test_mapper_adversarial_duplicate_hsp_ids(tmp_path):
    run_dir = materialize_run("adversarial", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "adversarial"))
    output = map_all(source)
    hsp_ids = [node["id"] for node in output.nodes if node["type"] == "HSP"]
    assert len(hsp_ids) == len(set(hsp_ids))
    aggregates = [node for node in output.nodes if node["type"] == "EvidenceAggregate"]
    for agg in aggregates:
        for input_id in agg["derivation"]["input_ids"]:
            hsp = next(n for n in output.nodes if n["id"] == input_id)
            assert hsp["observation"]["eligible"] is True
            assert hsp["observation"].get("rejection_reason") != "DUPLICATE_SOURCE_OBSERVATION"


def test_mapper_same_lineage_id_across_loci_distinct_nodes():
    from genein.evidence_graph.graph_builder.types import SourceArtifacts

    digest = {"sha256": "a" * 64, "size": 1}
    lineage_rows = [
        {
            "lineage_record_id": "TLR_a",
            "lineage_id": "LIN_shared",
            "sample_id": "s",
            "reference_id": "ref1",
            "locus_id": "LOCUS_1",
            "orientation": "+",
            "query_ids": "c1",
            "source_template_digests": "",
            "final_umi": "AAAA",
            "umi_group_method": "directional",
            "library_mode": "shotgun",
            "umi_mode": "tag",
            "template_count": "1",
            "read_count": "2",
            "mapped_bases": "100",
            "proper_pair_templates": "1",
            "discordant_templates": "0",
            "eligible": "true",
            "rejection_reason": "",
            "rule_id": "ADMIT-TEMPLATE-LINEAGE",
        },
        {
            "lineage_record_id": "TLR_b",
            "lineage_id": "LIN_shared",
            "sample_id": "s",
            "reference_id": "ref1",
            "locus_id": "LOCUS_2",
            "orientation": "+",
            "query_ids": "c1",
            "source_template_digests": "",
            "final_umi": "AAAA",
            "umi_group_method": "directional",
            "library_mode": "shotgun",
            "umi_mode": "tag",
            "template_count": "1",
            "read_count": "2",
            "mapped_bases": "80",
            "proper_pair_templates": "1",
            "discordant_templates": "0",
            "eligible": "true",
            "rejection_reason": "",
            "rule_id": "ADMIT-TEMPLATE-LINEAGE",
        },
    ]
    source = SourceArtifacts(
        run_id="run-shared-lineage",
        run_dir=Path("."),
        digests={
            "template_lineage.tsv": digest,
            "sample_evidence.json": digest,
            "provenance.json": digest,
            "run_state.json": digest,
        },
        tables={"template_lineage.tsv": lineage_rows},
        documents={
            "sample_evidence.json": {"sample_id": "s"},
            "provenance.json": {},
            "run_state.json": {},
        },
    )
    output = map_all(source)
    rs_ids = [node["id"] for node in output.nodes if node["type"] == "ReadSupport"]
    assert len(rs_ids) == 2
    assert len(set(rs_ids)) == 2
    loci = {node["locus_id"] for node in output.nodes if node["type"] == "ReadSupport"}
    assert loci == {"LOCUS_1", "LOCUS_2"}


def test_mapper_aggregates_into_source_ref_is_hsp_evidence(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "agg-src"))
    output = map_all(source)
    agg_edges = [edge for edge in output.edges if edge["type"] == "AGGREGATES_INTO"]
    assert agg_edges
    for edge in agg_edges:
        assert edge["provenance"]["source_ref"] == "hsp_evidence.tsv"
    aggregates = [node for node in output.nodes if node["type"] == "EvidenceAggregate"]
    assert aggregates
    for agg in aggregates:
        assert agg["provenance"]["source_ref"] == "hsp_evidence.tsv"


def test_mapper_assembly_method_not_from_concordance():
    from genein.evidence_graph.graph_builder.types import SourceArtifacts

    digest = {"sha256": "b" * 64, "size": 1}
    source = SourceArtifacts(
        run_id="run-asm",
        run_dir=Path("."),
        digests={
            "fragment_evidence.tsv": digest,
            "assembly_concordance.tsv": digest,
            "sample_evidence.json": digest,
            "provenance.json": digest,
            "run_state.json": digest,
        },
        tables={
            "fragment_evidence.tsv": [{
                "qseqid": "contig_x",
                "sseqid": "ref1",
                "qlen": "100",
                "sequence_sha256": "c" * 64,
                "assembly_method": "",
            }],
            "assembly_concordance.tsv": [{
                "reference_id": "ref1",
                "locus_id": "LOCUS_1",
                "query_ids": "contig_x",
                "supporting_assemblers": "spades;megahit",
            }],
        },
        documents={
            "sample_evidence.json": {"sample_id": "s"},
            "provenance.json": {},
            "run_state.json": {},
        },
    )
    output = map_all(source)
    contig = next(node for node in output.nodes if node["type"] == "Contig")
    assert contig["assembly_method"] is None
    assert contig["observation"]["eligible"] is False
    assert "assembly_method" in contig["observation"]["missing_fields"]
    assert contig["observation"]["rejection_reason"] == "MISSING_FIELD"


def test_mapper_readsupport_from_template_lineage(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "rs"))
    output = map_all(source)
    rs = next(node for node in output.nodes if node["type"] == "ReadSupport")
    assert rs["observation"]["eligible"] is False
    assert rs["lineage_id"] is None
    assert rs["read_count"] == 4
    assert rs["mapped_bases"] == 240
    assert "lineage_id" in rs["observation"]["missing_fields"]
    assert rs["provenance"]["source_ref"] == "template_lineage.tsv"


def test_mapper_readsupport_historical_abstention(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "hist-rs"))
    output = map_all(source)
    rs = next(node for node in output.nodes if node["type"] == "ReadSupport")
    assert rs["observation"]["eligible"] is False
    assert rs["lineage_id"] is None
    assert rs["read_count"] is None
    assert any("P-E5-2" in note for note in output.scope_notes)


def test_mapper_factual_edges_only(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "edges"))
    output = map_all(source)
    allowed = {
        "DERIVED_FROM", "PROCESSED_FROM", "SUPPORTS", "ASSEMBLED_FROM",
        "ALIGNS_TO", "MATCHES", "LOCATED_IN", "AGGREGATES_INTO",
    }
    assert output.edges
    assert {edge["type"] for edge in output.edges} <= allowed
    for edge in output.edges:
        assert edge["observed"] is True
        assert edge["decision_relevant"] is False
        assert edge["provenance"]["source_ref"]
        assert edge["provenance"]["source_digest"].startswith("sha256:")
        if edge["type"] in {"ALIGNS_TO", "MATCHES", "LOCATED_IN", "AGGREGATES_INTO"}:
            assert edge["eligible"] is True


def test_mapper_provenance_exact_reference(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "prov"))
    output = map_all(source)
    for node in output.nodes:
        prov = node["provenance"]
        assert prov["source_ref"] in source.digests
        assert prov["source_digest"] == digest_ref(source.digests, prov["source_ref"])
        if node["type"] == "Reference":
            assert prov["source_ref"] != "missing.tsv"


def test_mapper_one_observation_per_row(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    source = read(_request(run_dir, tmp_path / "output" / "one-obs"))
    output = map_all(source)
    assert len([n for n in output.nodes if n["type"] == "HSP"]) == len(source.tables["hsp_evidence.tsv"])
    assert len([n for n in output.nodes if n["type"] == "ReadSupport"]) == len(
        source.tables["template_lineage.tsv"]
    )


def test_pipeline_roundtrip(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    out_root = tmp_path / "pipeline-roundtrip"
    result = build(_request(run_dir, out_root))
    graph_path = result.graph_dir / "evidence_graph.json"
    assert graph_path.is_file()
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert graph["graph_id"] == "G-fixture-alpha2-run"
    assert graph["mapper_version"] == "0.2.2"
    assert "source_artifacts" in graph
    assert "source_manifest_digest" in graph
    assert "rule_catalog_digest" in graph
    assert graph["evaluation"] == []
    assert (result.graph_dir / "hsp_evidence.tsv").is_file()
    assert (result.graph_dir / "template_lineage.tsv").is_file()
    success = json.loads((result.graph_dir / "SUCCESS.json").read_text(encoding="utf-8"))
    assert success["mapper_version"] == "0.2.2"
    assert success["mapper_source_version"] == "0.2.2"
    # byte-identical sidecar copy
    assert sha256_file(result.graph_dir / "hsp_evidence.tsv") == sha256_file(run_dir / "hsp_evidence.tsv")
    assert sha256_file(result.graph_dir / "template_lineage.tsv") == sha256_file(
        run_dir / "template_lineage.tsv"
    )


def test_writer_preserves_existing_destination(tmp_path):
    run_dir = materialize_run("complete_with_hsp", root=tmp_path)
    out_root = tmp_path / "writer-existing"
    first = build(_request(run_dir, out_root))
    marker = first.graph_dir / "SUCCESS.json"
    original = marker.read_text(encoding="utf-8")
    with pytest.raises(DestinationExistsError):
        build(_request(run_dir, out_root))
    assert marker.read_text(encoding="utf-8") == original


def test_writer_does_not_promote_invalid_graph(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    request = _request(run_dir, tmp_path)
    graph = {
        "graph_id": "G-invalid-test",
        "created_at": "2026-08-18T00:00:00Z",
    }

    with pytest.raises(ValueError, match="mantidos somente em staging"):
        write(request, graph, {"valid": False}, source_digests={})

    assert not (tmp_path / "G-invalid-test").exists()
    assert (tmp_path / ".staging-G-invalid-test").is_dir()
    assert not (tmp_path / ".staging-G-invalid-test" / "SUCCESS.json").exists()


def test_writer_concurrent_staging(tmp_path):
    run_dir = materialize_run("no_hsp", root=tmp_path)
    request = _request(run_dir, tmp_path)
    staging = tmp_path / ".staging-G-concurrent"
    staging.mkdir(parents=True)
    (staging / "lock").write_text("busy", encoding="utf-8")
    with pytest.raises(StagingConflictError):
        write(
            request,
            {"graph_id": "G-concurrent", "created_at": "2026-08-18T00:00:00Z"},
            {"valid": True},
            source_digests={},
        )


def test_integration_repo_alpha2_complete(tmp_path):
    if not ALPHA2.is_dir():
        pytest.skip("alpha2_complete fixture unavailable")
    errors = verify_promotion(_request(ALPHA2, tmp_path / "output" / "repo-alpha2"))
    assert errors == []
