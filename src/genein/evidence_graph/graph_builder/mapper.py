"""2. Mapper — projeta artefatos em nós e arestas factuais v0.2.2."""
from __future__ import annotations

from typing import Any

from genein.evidence_graph.graph_builder.parse import (
    HSP_EVIDENCE_COLUMNS,
    TEMPLATE_LINEAGE_COLUMNS,
    admit_coord_system,
    admit_strand,
    empty_to_none,
    node_id,
    parse_bool_cell,
    parse_interval_list,
    safe_float,
    safe_int,
    utc_now_iso,
)
from genein.evidence_graph.graph_builder.provenance import builder_provenance
from genein.evidence_graph.graph_builder.types import MapperOutput, SourceArtifacts

RULE_IDS = {
    "DERIVED_FROM": "ADMIT-DERIVED_FROM",
    "PROCESSED_FROM": "ADMIT-PROCESSED_FROM",
    "SUPPORTS": "ADMIT-SUPPORTS",
    "ASSEMBLED_FROM": "ADMIT-ASSEMBLED_FROM",
    "ALIGNS_TO": "ADMIT-ALIGNS_TO",
    "MATCHES": "ADMIT-MATCHES",
    "LOCATED_IN": "ADMIT-LOCATED_IN",
    "AGGREGATES_INTO": "ADMIT-AGGREGATES_INTO",
}

FACTUAL_HSP_FIELDS = (
    "query_length",
    "alignment_length",
    "identity_pct",
    "matches",
    "mismatches",
    "gaps",
    "evalue",
    "bitscore",
    "strand",
    "coord_system",
)


def _observation(
    *,
    eligible: bool,
    raw: dict[str, Any],
    missing_fields: list[str] | None = None,
    rejection_reason: str | None = None,
    rule_id: str = "ADMIT-MAPPER",
) -> dict[str, Any]:
    obs: dict[str, Any] = {
        "observed": True,
        "eligible": eligible,
        "raw": raw,
        "rule_id": rule_id,
    }
    if not eligible:
        obs["status"] = "NOT_EVALUABLE"
        obs["rejection_reason"] = rejection_reason or "MISSING_FIELD"
        obs["missing_fields"] = list(missing_fields or [])
    return obs


def _edge(
    source: str,
    target: str,
    edge_type: str,
    *,
    digests: dict[str, dict[str, Any]],
    source_ref: str,
    eligible: bool = True,
    rejection_reason: str | None = None,
    edge_index: int,
) -> dict[str, Any]:
    edge: dict[str, Any] = {
        "id": f"E-{edge_type}-{edge_index}",
        "type": edge_type,
        "source": source,
        "target": target,
        "observed": True,
        "eligible": eligible,
        "decision_relevant": False,
        "rule_id": RULE_IDS[edge_type],
        "provenance": builder_provenance(
            source_ref=source_ref,
            digests=digests,
            method=f"mapper.map_factual_edges:{edge_type}",
        ),
        "created_at": utc_now_iso(),
    }
    if not eligible:
        edge["rejection_reason"] = rejection_reason or "MISSING_FIELD"
    return edge


def map_sample_and_run(source: SourceArtifacts) -> list[dict[str, Any]]:
    sample_doc = source.documents.get("sample_evidence.json", {})
    provenance_doc = source.documents.get("provenance.json", {})
    run_state = source.documents.get("run_state.json", {})
    sample_id = str(sample_doc.get("sample_id") or source.run_id)
    nodes = [
        {
            "id": node_id("S", sample_id),
            "type": "Sample",
            "sample_ref": sample_id,
            "provenance": builder_provenance(
                source_ref="sample_evidence.json",
                digests=source.digests,
                method="mapper.map_sample_and_run:Sample",
                parameters={"sample_id": sample_id},
            ),
        },
        {
            "id": node_id("R", source.run_id),
            "type": "Run",
            "run_ref": source.run_id,
            "toolchain": {
                "pipeline_version": provenance_doc.get("pipeline_version") or sample_doc.get("pipeline_version"),
                "policy_version": run_state.get("policy_version"),
                "tools": provenance_doc.get("tools", {}),
            },
            "provenance": builder_provenance(
                source_ref="provenance.json",
                digests=source.digests,
                method="mapper.map_sample_and_run:Run",
                parameters=provenance_doc.get("parameters", {}),
            ),
        },
    ]
    return nodes


def _reference_source_ref(source: SourceArtifacts, ref: str) -> str:
    """Proveniência aponta para um artefato que de fato contém a referência."""
    for table_name in (
        "fragment_evidence.tsv",
        "locus_evidence.tsv",
        "hsp_evidence.tsv",
        "template_lineage.tsv",
        "read_support.tsv",
        "coverage.tsv",
        "competitive_hits.tsv",
    ):
        if table_name not in source.digests:
            continue
        for row in source.tables.get(table_name, []):
            if row.get("sseqid") == ref or row.get("reference_id") == ref:
                return table_name
    raise ValueError(f"referência sem artefato de origem: {ref}")


def map_references(source: SourceArtifacts) -> list[dict[str, Any]]:
    reference_ids: set[str] = set()
    for table_name, rows in source.tables.items():
        if table_name not in source.digests:
            continue
        for row in rows:
            ref = empty_to_none(row.get("sseqid")) or empty_to_none(row.get("reference_id"))
            if ref:
                reference_ids.add(ref)
    nodes: list[dict[str, Any]] = []
    for ref in sorted(reference_ids):
        source_ref = _reference_source_ref(source, ref)
        nodes.append({
            "id": node_id("REF", ref),
            "type": "Reference",
            "reference_ref": ref,
            "provenance": builder_provenance(
                source_ref=source_ref,
                digests=source.digests,
                method="mapper.map_references",
                parameters={"reference_id": ref},
            ),
        })
    return nodes


def map_contigs(source: SourceArtifacts) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in source.tables.get("fragment_evidence.tsv", []):
        qseqid = empty_to_none(row.get("qseqid"))
        if not qseqid or qseqid in seen:
            continue
        seen.add(qseqid)
        # Never infer assembly_method from assembly_concordance.tsv.
        asm = empty_to_none(row.get("assembly_method"))
        seq_hex = empty_to_none(row.get("sequence_sha256"))
        length = safe_int(row.get("qlen"))
        missing: list[str] = []
        if asm is None:
            missing.append("assembly_method")
        if length is None:
            missing.append("length")
        if seq_hex is None:
            missing.append("sequence_digest")
        nodes.append({
            "id": node_id("C", qseqid),
            "type": "Contig",
            "contig_ref": qseqid,
            "length": length,
            "assembly_method": asm,
            "sequence_digest": f"sha256:{seq_hex}" if seq_hex else None,
            "observation": _observation(
                eligible=not missing,
                raw=dict(row),
                missing_fields=missing or None,
                rejection_reason="MISSING_FIELD" if missing else None,
                rule_id="ADMIT-CONTIG",
            ),
            "provenance": builder_provenance(
                source_ref="fragment_evidence.tsv",
                digests=source.digests,
                method="mapper.map_contigs",
                parameters={"qseqid": qseqid},
            ),
        })
    return nodes


def map_loci(source: SourceArtifacts) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for row in source.tables.get("locus_evidence.tsv", []):
        locus_key = empty_to_none(row.get("locus_id"))
        if not locus_key:
            continue
        intervals = parse_interval_list(str(row.get("reference_intervals", "")))
        coord, coord_ok, coord_reason = admit_coord_system(row.get("coord_system"))
        ref = empty_to_none(row.get("sseqid"))
        missing: list[str] = []
        if not intervals:
            missing.append("interval")
        if not coord_ok:
            missing.append("coord_system")
        if ref is None:
            missing.append("reference_id")
        nodes.append({
            "id": node_id("LOC", locus_key),
            "type": "Locus",
            "reference_id": ref,
            "interval": intervals if intervals else None,
            "coord_system": coord,
            "observation": _observation(
                eligible=not missing,
                raw=dict(row),
                missing_fields=missing or None,
                rejection_reason=(
                    coord_reason if not coord_ok else ("MISSING_FIELD" if missing else None)
                ),
                rule_id="ADMIT-LOCUS",
            ),
            "provenance": builder_provenance(
                source_ref="locus_evidence.tsv",
                digests=source.digests,
                method="mapper.map_loci",
                parameters={"locus_id": locus_key},
            ),
        })
    return nodes


def _canonical_hsp_row(row: dict[str, str], hsp_key: str) -> dict[str, Any]:
    out = {col: row.get(col, "") for col in HSP_EVIDENCE_COLUMNS}
    out["hsp_id"] = hsp_key
    return out


def map_hsps(source: SourceArtifacts) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    hsp_table = source.tables.get("hsp_evidence.tsv")
    if hsp_table is None:
        return [], [], ["P-E5-1: hsp_evidence.tsv ausente — escopo HSP NOT_EVALUABLE; sem reconstrução de agregados"]

    nodes: list[dict[str, Any]] = []
    rows_out: list[dict[str, Any]] = []
    seen_keys: dict[str, str] = {}

    for index, row in enumerate(hsp_table):
        base_key = empty_to_none(row.get("hsp_id")) or f"hsp-{index}"
        duplicate_of = empty_to_none(row.get("duplicate_of_hsp_id"))
        declared_dup = parse_bool_cell(row.get("eligible")) is False and (
            empty_to_none(row.get("rejection_reason")) == "DUPLICATE_SOURCE_OBSERVATION"
            or duplicate_of is not None
        )
        if base_key in seen_keys:
            hsp_key = f"{base_key}#dup{index}"
            duplicate_of = duplicate_of or seen_keys[base_key]
            declared_dup = True
        else:
            hsp_key = base_key
            seen_keys[base_key] = hsp_key

        coord, coord_ok, coord_reason = admit_coord_system(row.get("coord_system"))
        strand = admit_strand(row.get("strand"))
        values = {
            "query_length": safe_int(row.get("query_length")),
            "alignment_length": safe_int(row.get("alignment_length")),
            "identity_pct": safe_float(row.get("identity_pct")),
            "matches": safe_int(row.get("matches")),
            "mismatches": safe_int(row.get("mismatches")),
            "gaps": safe_int(row.get("gaps")),
            "evalue": safe_float(row.get("evalue")),
            "bitscore": safe_float(row.get("bitscore")),
            "strand": strand,
            "coord_system": coord if coord_ok else None,
        }
        missing = [field for field in FACTUAL_HSP_FIELDS if values[field] is None]

        rejection = empty_to_none(row.get("rejection_reason"))
        rule_id = empty_to_none(row.get("rule_id")) or "ADMIT-HSP"
        if declared_dup:
            eligible = False
            rejection = "DUPLICATE_SOURCE_OBSERVATION"
            if "duplicate_of_hsp_id" not in missing and duplicate_of is None:
                missing = [*missing, "duplicate_of_hsp_id"] if "duplicate_of_hsp_id" not in missing else missing
        elif parse_bool_cell(row.get("eligible")) is False:
            eligible = False
            rejection = rejection or ("INVALID_COORDINATES" if not coord_ok else "MISSING_FIELD")
        else:
            eligible = not missing
            if not eligible:
                rejection = coord_reason if not coord_ok else "MISSING_FIELD"

        rows_out.append(_canonical_hsp_row(row, hsp_key))
        if declared_dup and duplicate_of:
            rows_out[-1]["duplicate_of_hsp_id"] = duplicate_of
            rows_out[-1]["eligible"] = "false"
            rows_out[-1]["rejection_reason"] = "DUPLICATE_SOURCE_OBSERVATION"
            rows_out[-1]["rule_id"] = rule_id

        node = {
            "id": node_id("HSP", hsp_key),
            "type": "HSP",
            "hsp_ref": hsp_key,
            **values,
            "observation": _observation(
                eligible=eligible,
                raw=dict(row),
                missing_fields=missing if not eligible else None,
                rejection_reason=rejection if not eligible else None,
                rule_id=rule_id,
            ),
            "provenance": builder_provenance(
                source_ref="hsp_evidence.tsv",
                digests=source.digests,
                method="mapper.map_hsps",
                parameters={"hsp_id": hsp_key},
            ),
            "_qseqid": empty_to_none(row.get("qseqid")),
            "_sseqid": empty_to_none(row.get("sseqid")),
            "_locus_id": empty_to_none(row.get("locus_id")),
        }
        nodes.append(node)
    return nodes, rows_out, []


def _canonical_lineage_row(row: dict[str, str], record_id: str) -> dict[str, Any]:
    out = {col: row.get(col, "") for col in TEMPLATE_LINEAGE_COLUMNS}
    out["lineage_record_id"] = record_id
    return out


def map_read_support(
    source: SourceArtifacts,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    lineage_table = source.tables.get("template_lineage.tsv")
    notes: list[str] = []
    nodes: list[dict[str, Any]] = []
    rows_out: list[dict[str, Any]] = []

    if lineage_table is not None:
        for index, row in enumerate(lineage_table):
            record_id = empty_to_none(row.get("lineage_record_id")) or f"lineage-record-{index}"
            lineage_id = empty_to_none(row.get("lineage_id"))
            locus_id = empty_to_none(row.get("locus_id")) or "unknown"
            read_count = safe_int(row.get("read_count"))
            mapped_bases = safe_int(row.get("mapped_bases"))
            missing: list[str] = []
            if lineage_id is None:
                missing.append("lineage_id")
            if read_count is None:
                missing.append("read_count")
            if mapped_bases is None:
                missing.append("mapped_bases")

            declared_eligible = parse_bool_cell(row.get("eligible"))
            rejection = empty_to_none(row.get("rejection_reason"))
            rule_id = empty_to_none(row.get("rule_id")) or "ADMIT-READSUPPORT"
            if declared_eligible is False:
                eligible = False
                rejection = rejection or "MISSING_FIELD"
            else:
                eligible = not missing
                if not eligible:
                    rejection = "MISSING_FIELD"

            support_key = f"{locus_id}:{lineage_id or record_id}"
            nodes.append({
                "id": node_id("RS", support_key),
                "type": "ReadSupport",
                "support_ref": support_key,
                "lineage_id": lineage_id,
                "locus_id": locus_id,
                "read_count": read_count,
                "mapped_bases": mapped_bases,
                "observation": _observation(
                    eligible=eligible,
                    raw=dict(row),
                    missing_fields=missing if not eligible else None,
                    rejection_reason=rejection if not eligible else None,
                    rule_id=rule_id,
                ),
                "provenance": builder_provenance(
                    source_ref="template_lineage.tsv",
                    digests=source.digests,
                    method="mapper.map_read_support",
                    parameters={"lineage_record_id": record_id},
                ),
                "_query_ids": row.get("query_ids", ""),
                "_source_ref": "template_lineage.tsv",
            })
            rows_out.append(_canonical_lineage_row(row, record_id))
        return nodes, rows_out, notes

    # Histórico sem sidecar: read_support.tsv vira observação inelegível (P-E5-2).
    notes.append(
        "P-E5-2: template_lineage.tsv ausente — ReadSupport derivado de read_support.tsv "
        "como observação NOT_EVALUABLE (território umi_mode/histórico)"
    )
    for index, row in enumerate(source.tables.get("read_support.tsv", [])):
        locus_key = empty_to_none(row.get("locus_id")) or "unknown"
        orientation = empty_to_none(row.get("orientation")) or "NA"
        support_key = f"{locus_key}:{orientation}:{index}"
        missing = ["lineage_id", "read_count", "mapped_bases"]
        nodes.append({
            "id": node_id("RS", support_key),
            "type": "ReadSupport",
            "support_ref": support_key,
            "lineage_id": None,
            "locus_id": locus_key,
            "read_count": None,
            "mapped_bases": None,
            "observation": _observation(
                eligible=False,
                raw=dict(row),
                missing_fields=missing,
                rejection_reason="MISSING_FIELD",
                rule_id="ADMIT-READSUPPORT",
            ),
            "provenance": builder_provenance(
                source_ref="read_support.tsv",
                digests=source.digests,
                method="mapper.map_read_support:historical",
                parameters={"locus_id": locus_key},
            ),
            "_query_ids": row.get("query_ids", ""),
            "_source_ref": "read_support.tsv",
        })
        rows_out.append({
            "lineage_record_id": support_key,
            "lineage_id": "",
            "sample_id": row.get("sample_id", ""),
            "reference_id": row.get("reference_id", ""),
            "locus_id": locus_key,
            "orientation": orientation,
            "query_ids": row.get("query_ids", ""),
            "source_template_digests": "",
            "final_umi": "",
            "umi_group_method": "",
            "library_mode": row.get("library_mode", ""),
            "umi_mode": row.get("umi_mode", ""),
            "template_count": row.get("unique_templates", ""),
            "read_count": "",
            "mapped_bases": "",
            "proper_pair_templates": row.get("proper_pair_templates", ""),
            "discordant_templates": row.get("discordant_templates", ""),
            "eligible": "false",
            "rejection_reason": "MISSING_FIELD",
            "rule_id": "ADMIT-TEMPLATE-LINEAGE",
        })
    return nodes, rows_out, notes


def map_factual_edges(source: SourceArtifacts, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        by_type.setdefault(node["type"], []).append(node)

    sample = next(n for n in nodes if n["type"] == "Sample")
    run = next(n for n in nodes if n["type"] == "Run")
    contig_by_ref = {n["contig_ref"]: n["id"] for n in by_type.get("Contig", [])}
    ref_by_ref = {n["reference_ref"]: n["id"] for n in by_type.get("Reference", [])}
    locus_by_key = {
        empty_to_none(row.get("locus_id")): node_id("LOC", row["locus_id"])
        for row in source.tables.get("locus_evidence.tsv", [])
        if empty_to_none(row.get("locus_id"))
    }

    edges: list[dict[str, Any]] = []
    idx = 0

    def add(
        source_id: str,
        target_id: str,
        edge_type: str,
        source_ref: str,
        *,
        eligible: bool = True,
        rejection_reason: str | None = None,
    ) -> None:
        nonlocal idx
        edges.append(
            _edge(
                source_id,
                target_id,
                edge_type,
                digests=source.digests,
                source_ref=source_ref,
                eligible=eligible,
                rejection_reason=rejection_reason,
                edge_index=idx,
            )
        )
        idx += 1

    add(run["id"], sample["id"], "DERIVED_FROM", "provenance.json")

    for rs in by_type.get("ReadSupport", []):
        source_ref = rs.get("_source_ref") or "read_support.tsv"
        rs_eligible = rs.get("observation", {}).get("eligible") is True
        add(
            rs["id"],
            run["id"],
            "PROCESSED_FROM",
            source_ref,
            eligible=rs_eligible,
            rejection_reason=None if rs_eligible else rs.get("observation", {}).get("rejection_reason"),
        )
        for qid in str(rs.get("_query_ids", "")).split(";"):
            qid = qid.strip()
            if qid and qid in contig_by_ref:
                # Arestas factuais SUPPORTS/ASSEMBLED_FROM só quando ReadSupport elegível.
                if rs_eligible:
                    add(rs["id"], contig_by_ref[qid], "SUPPORTS", source_ref)
                    add(contig_by_ref[qid], rs["id"], "ASSEMBLED_FROM", "fragment_evidence.tsv")

    for hsp in by_type.get("HSP", []):
        qid = hsp.get("_qseqid")
        sid = hsp.get("_sseqid")
        eligible = hsp.get("observation", {}).get("eligible") is True
        reason = hsp.get("observation", {}).get("rejection_reason")
        # Arestas factuais de alinhamento só para HSP elegível (sem placeholders).
        if not eligible:
            continue
        if qid and qid in contig_by_ref:
            add(hsp["id"], contig_by_ref[qid], "ALIGNS_TO", "hsp_evidence.tsv")
        if sid and sid in ref_by_ref:
            add(hsp["id"], ref_by_ref[sid], "MATCHES", "hsp_evidence.tsv")
        locus_key = hsp.get("_locus_id")
        if locus_key and locus_key in locus_by_key:
            add(hsp["id"], locus_by_key[locus_key], "LOCATED_IN", "hsp_evidence.tsv")

    for node in nodes:
        for key in ("_qseqid", "_sseqid", "_locus_id", "_query_ids", "_source_ref"):
            node.pop(key, None)

    return edges


def map_aggregates(
    source: SourceArtifacts,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hsp_nodes = [n for n in nodes if n["type"] == "HSP"]
    if not hsp_nodes:
        return []

    hsp_by_locus: dict[str, list[dict[str, Any]]] = {}
    for hsp in hsp_nodes:
        raw = hsp.get("observation", {}).get("raw", {})
        locus_key = empty_to_none(raw.get("locus_id"))
        if locus_key:
            hsp_by_locus.setdefault(locus_key, []).append(hsp)

    aggregates: list[dict[str, Any]] = []
    edge_index = len(edges)

    for row in source.tables.get("locus_evidence.tsv", []):
        locus_key = empty_to_none(row.get("locus_id"))
        if not locus_key or locus_key not in hsp_by_locus:
            continue
        eligible_hsps = [
            hsp for hsp in hsp_by_locus[locus_key]
            if hsp.get("observation", {}).get("eligible") is True
        ]
        if not eligible_hsps:
            continue
        ref = empty_to_none(row.get("sseqid"))
        locus_nid = node_id("LOC", locus_key)
        locus_node = next((n for n in nodes if n["type"] == "Locus" and n["id"] == locus_nid), None)
        if not locus_node or ref is None:
            continue
        ref_nid = next(
            (n["id"] for n in nodes if n["type"] == "Reference" and n["reference_ref"] == ref),
            None,
        )
        if not ref_nid:
            continue
        agg_id = node_id("AGG", f"{locus_key}:{ref}")
        eligible_ids = [hsp["id"] for hsp in eligible_hsps]
        aggregates.append({
            "id": agg_id,
            "type": "EvidenceAggregate",
            "locus_id": locus_node["id"],
            "hypothesis": {"reference_ids": [ref_nid]},
            "aggregation_method": "UNION_ALL_ELIGIBLE",
            "derivation": {"input_ids": eligible_ids, "evaluator_version": "mapper-v0.2.2"},
            "provenance": builder_provenance(
                source_ref="hsp_evidence.tsv",
                digests=source.digests,
                method="mapper.map_aggregates",
                parameters={"locus_id": locus_key},
            ),
        })
        for hid in eligible_ids:
            edges.append(
                _edge(
                    hid,
                    agg_id,
                    "AGGREGATES_INTO",
                    digests=source.digests,
                    source_ref="hsp_evidence.tsv",
                    eligible=True,
                    edge_index=edge_index,
                )
            )
            edge_index += 1

    return aggregates


def map_all(source: SourceArtifacts) -> MapperOutput:
    """Executa o mapeamento completo e produz TSVs derivados."""
    nodes = map_sample_and_run(source)
    nodes.extend(map_references(source))
    nodes.extend(map_contigs(source))
    nodes.extend(map_loci(source))
    hsp_nodes, hsp_rows, hsp_notes = map_hsps(source)
    nodes.extend(hsp_nodes)
    rs_nodes, lineage_rows, rs_notes = map_read_support(source)
    nodes.extend(rs_nodes)
    scope_notes = [*hsp_notes, *rs_notes]
    edges = map_factual_edges(source, nodes)
    aggregates = map_aggregates(source, nodes, edges)
    nodes.extend(aggregates)
    return MapperOutput(
        nodes=nodes,
        edges=edges,
        aggregates=aggregates,
        hsp_evidence_rows=hsp_rows,
        template_lineage_rows=lineage_rows,
        scope_notes=scope_notes,
    )
