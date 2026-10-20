#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common import as_float, as_int, format_intervals, interval_size, parse_intervals, read_tsv, write_json_atomic
    from .activation_policy import (
        conclusion_for,
        load_experimental_activation_policy,
        load_public_activation_policy,
        policy_identity,
    )
    from .evidence_contract import PIPELINE_VERSION, SCHEMA_VERSION, validate_document
except ImportError:
    from common import as_float, as_int, format_intervals, interval_size, parse_intervals, read_tsv, write_json_atomic
    from activation_policy import (
        conclusion_for,
        load_experimental_activation_policy,
        load_public_activation_policy,
        policy_identity,
    )
    from evidence_contract import PIPELINE_VERSION, SCHEMA_VERSION, validate_document


def _required_section(thresholds: dict, name: str) -> dict:
    section = thresholds.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"policy thresholds.{name} must be an object")
    return section


def _metric_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("reference_id") or row.get("reference") or ""),
        str(row.get("category") or ""),
        str(row.get("locus_id") or ""),
    )


def _index_scoped_metrics(rows: list[dict], name: str) -> tuple[dict[tuple[str, str, str], dict], list[str]]:
    result: dict[tuple[str, str, str], dict] = {}
    caveats: list[str] = []
    for row_number, row in enumerate(rows, 2):
        key = _metric_key(row)
        if not all(key):
            caveats.append(f"{name} sem reference/category/locus na linha {row_number}; métrica ignorada.")
            continue
        if key in result:
            raise ValueError(f"duplicate {name} metric key: {key}")
        result[key] = row
    return result, caveats


def _candidate_key(locus: dict) -> tuple[str, str, str]:
    return (
        str(locus.get("sseqid") or locus.get("reference_id") or ""),
        str(locus.get("category") or "UNLABELED"),
        str(locus.get("locus_id") or ""),
    )


SCIENCE_REVISION = "scientific_review_20261005_v1"


def _combined_status(statuses):
    if statuses and all(status == "TARGET_SPECIFIC" for status in statuses):
        return "TARGET_SPECIFIC"
    if "NON_TARGET_BEST" in statuses and "TARGET_SPECIFIC" not in statuses:
        return "NON_TARGET_BEST"
    if any(status in {"AMBIGUOUS", "NON_TARGET_BEST"} for status in statuses):
        return "AMBIGUOUS"
    return "NOT_EVALUATED"


def _reference_competition(rows):
    indexed = {}
    for row in rows:
        key = (row["qseqid"], row.get("task", "blastn"))
        if key in indexed:
            raise ValueError(f"duplicate competitive query/task: {key}")
        details = row.get("target_evidence_json")
        if details:
            values = json.loads(details)
            if not isinstance(values, list):
                raise ValueError("target_evidence_json must be an array")
            references = {}
            for item in values:
                if not isinstance(item, dict) or not item.get("reference_id"):
                    raise ValueError("competitive reference_id is required")
                if item["reference_id"] in references:
                    raise ValueError("duplicate competitive reference_id")
                references[item["reference_id"]] = item
            indexed[key] = references
        else:
            # Existing artifacts identify only their best target. Never copy
            # that target's status to a different locus/reference.
            reference = row.get("target_sseqid")
            indexed[key] = {reference: {
                "specificity_status": row.get("specificity_status", "NOT_EVALUATED"),
                "taxonomic_status": "NOT_EVALUATED",
                "taxonomic_flags": ["LEGACY_COMPETITION_WITHOUT_TAXON_COMPARISON"],
            }} if reference else {}
    return indexed


def reference_coverage(candidates):
    """Union reference positions across strands, loci and BLAST profiles.

    Missing intervals cannot be reconstructed from a count; report missing
    measurements explicitly rather than inventing reference coordinates.
    """
    grouped = {}
    for candidate in candidates:
        key = (candidate["reference_id"], candidate["segment"])
        entry = grouped.setdefault(key, {"intervals": [], "missing": 0, "length": 0})
        length = candidate["reference_length"]
        if length:
            if entry["length"] and entry["length"] != length:
                raise ValueError(f"inconsistent reference length: {key}")
            entry["length"] = length
        intervals = parse_intervals(candidate["reference_intervals"])
        if not intervals:
            entry["missing"] += 1
        if any(start < 1 or end < start for start, end in intervals):
            raise ValueError("invalid reference intervals")
        entry["intervals"].extend(intervals)
    output = []
    for (reference, segment), entry in sorted(grouped.items()):
        if entry["length"] and any(end > entry["length"] for _, end in entry["intervals"]):
            raise ValueError(f"reference interval exceeds reference length: {reference}")
        measured = bool(entry["intervals"])
        output.append({
            "reference_id": reference, "segment": segment,
            "reference_length": entry["length"] or None,
            "reference_intervals": format_intervals(entry["intervals"]),
            "aligned_reference_bp": interval_size(entry["intervals"]),
            "status": "PARTIAL" if measured and entry["missing"] else "AVAILABLE" if measured else "NOT_EVALUATED",
        })
    return output


def classify(sample: str, loci: list[dict[str, str]], competitive: list[dict[str, str]],
             read_support: list[dict[str, str]], coverage: list[dict[str, str]],
             control_status: str, library_mode: str, shadow: bool = False,
             provenance: dict | None = None, run_id: str | None = None,
             policy: dict | None = None,
             assembly_concordance: dict | None = None,
             historical_compatibility: str | None = None) -> dict:
    if not isinstance(shadow, bool):
        raise ValueError("shadow_mode must be boolean")
    if historical_compatibility is not None:
        if historical_compatibility != "historical_alpha2_fixture" or shadow is not True:
            raise ValueError("unsupported historical classification context")
        active_policy = load_public_activation_policy()
        identity = None
    else:
        active_policy = policy or load_public_activation_policy()
        identity = policy_identity(active_policy)
        if shadow is not active_policy["shadow_mode"]:
            raise ValueError("classification shadow_mode does not match the selected policy")

    provenance = provenance or {}
    assembly_concordance = assembly_concordance or {}
    assembly_by_locus = assembly_concordance.get("by_locus", {})
    if not isinstance(assembly_by_locus, dict):
        raise ValueError("assembly concordance by_locus must be an object")
    thresholds = active_policy["thresholds"]
    locus_cfg = _required_section(thresholds, "locus")
    evidence_cfg = _required_section(thresholds, "sample_evidence")
    parameters = provenance.get("parameters", {}) if isinstance(provenance, dict) else {}
    resolved_run_id = str(run_id or parameters.get("run_id") or provenance.get("run_id") or f"untracked-{sample}")
    comp_by_query = _reference_competition(competitive)
    support_by_key, support_caveats = _index_scoped_metrics(read_support, "read_support")
    coverage_by_key, coverage_caveats = _index_scoped_metrics(coverage, "coverage")

    evaluated_candidates = []
    all_specificity: list[str] = []
    for locus in loci:
        category = locus.get("category", "UNLABELED")
        if category not in {"TARGET_VIRUS", "UNLABELED"}:
            continue
        query_ids = list(filter(None, locus.get("query_ids", "").split(";")))
        reference_id = str(locus.get("sseqid") or locus.get("reference_id") or "")
        competition = [comp_by_query.get((query_id, locus.get("task", "blastn")), {}).get(reference_id, {})
                       for query_id in query_ids]
        query_statuses = [item.get("specificity_status", "NOT_EVALUATED") for item in competition]
        all_specificity.extend(query_statuses)
        specificity_status = _combined_status(query_statuses)
        taxonomic_statuses = [item.get("taxonomic_status", "NOT_EVALUATED") for item in competition]
        taxonomic_status = (
            "PANEL_TAXON_PREFERRED" if taxonomic_statuses and all(s == "PANEL_TAXON_PREFERRED" for s in taxonomic_statuses)
            else "NON_TARGET_BEST" if "NON_TARGET_BEST" in taxonomic_statuses and "PANEL_TAXON_PREFERRED" not in taxonomic_statuses
            else "AMBIGUOUS" if any(s in {"AMBIGUOUS", "NON_TARGET_BEST"} for s in taxonomic_statuses)
            else "NOT_EVALUATED"
        )
        key = _candidate_key(locus)
        support = support_by_key.get(key)
        covered = coverage_by_key.get(key)
        aligned_query_bp = as_int(locus.get("max_query_covered_bp"))
        query_length = as_int(locus.get("max_query_length"))
        # Apply the existing candidate-length policy to the query span that
        # actually aligned. Older canonical tables fall back to query length,
        # then to the nonredundant reference span for compatibility.
        candidate_bp = (
            aligned_query_bp
            or query_length
            or as_int(locus.get("covered_reference_bp"))
        )
        assembly_key = "|".join(key)
        assembly_support = assembly_by_locus.get(assembly_key, {
            "supporting_assemblers": [],
            "support_count": 0,
            "status": "NOT_EVALUATED",
        })
        evaluated_candidates.append({
            "candidate_id": locus.get("locus_id") or f"{key[0]}:{locus.get('reference_start', '')}-{locus.get('reference_end', '')}",
            "reference_id": key[0],
            "category": key[1],
            "locus_id": key[2],
            "query_ids": query_ids,
            "orientation": locus.get("orientation", ""),
            "segment": locus.get("segment", "unsegmented"),
            "task": locus.get("task", "blastn"),
            "taxon": str(locus.get("taxon") or ""),
            "reference_intervals": locus.get("reference_intervals", ""),
            "reference_length": as_int(locus.get("reference_length")),
            "specificity_status": specificity_status,
            "taxonomic_status": taxonomic_status,
            "taxonomic_scope": "REPORTED_LABELLED_PANEL_ONLY",
            "taxonomic_flags": sorted({flag for item in competition for flag in item.get("taxonomic_flags", [])}),
            "covered_reference_bp": as_int(locus.get("covered_reference_bp")),
            "candidate_bp": candidate_bp,
            "support": {
                "status": support.get("support_status", "NOT_EVALUATED") if support else "NOT_EVALUATED",
                "unique_templates": as_int(support.get("unique_templates")) if support else 0,
                "distinct_starts": as_int(support.get("distinct_starts")) if support else 0,
                "proper_pair_templates": as_int(support.get("proper_pair_templates")) if support else 0,
            },
            "coverage": {
                "status": "AVAILABLE" if covered else "NOT_EVALUATED",
                "breadth_1x": as_float(covered.get("breadth_1x")) if covered else 0.0,
                "breadth_3x": as_float(covered.get("breadth_3x")) if covered else 0.0,
                "median_depth_covered": as_float(covered.get("median_depth_covered")) if covered else 0.0,
                "max_window_depth_fraction": as_float(covered.get("max_window_depth_fraction")) if covered else 0.0,
            },
            "assembly_support": assembly_support,
        })

    specificity_status = _combined_status(all_specificity)

    minimum_candidate_bp = as_int(locus_cfg["minimum_candidate_bp"])
    for candidate in evaluated_candidates:
        candidate["candidate_class"] = (
            "EXPLORATORY_FRAGMENT"
            if candidate["candidate_bp"] < minimum_candidate_bp
            else "LOCUS_CANDIDATE"
        )
        candidate["promotion_status"] = "AVAILABLE"
        candidate["blocking_reasons"] = []
        candidate["availability_status"] = "AVAILABLE_FOR_REVIEW"
        candidate["qualification_status"] = "NOT_EVALUATED"

    candidates = evaluated_candidates
    aligned_references = reference_coverage(candidates)
    matched_support = [item["support"] for item in candidates]
    matched_coverage = [
        item["coverage"] for item in candidates
        if item["coverage"]["status"] == "AVAILABLE"
    ]
    coverage_passes = [
        item for item in matched_coverage
        if item["breadth_1x"] >= as_float(evidence_cfg["genome_breadth_1x"])
        and item["median_depth_covered"] >= as_float(evidence_cfg["median_covered_depth"])
    ]
    if any(item["support"]["status"] == "UMI_DEDUP_UNAVAILABLE" for item in evaluated_candidates):
        coverage_status = "UMI_DEDUP_UNAVAILABLE"
    elif matched_coverage:
        coverage_status = "COVERAGE_AVAILABLE" if coverage_passes else "INSUFFICIENT_COVERAGE"
    else:
        coverage_status = "COVERAGE_UNAVAILABLE"
    analysis_outcome = "EVIDENCE_RECOVERED" if candidates else "NO_EVIDENCE_RECOVERED"
    caveats = [*support_caveats, *coverage_caveats]
    if candidates:
        caveats.append("Candidatos recuperados para triagem humana; DETECTED é o código de recuperação, não confirmação de origem viral ou espécie.")
        if specificity_status == "NON_TARGET_BEST":
            caveats.append("O melhor alinhamento competitivo é de um não alvo; os candidatos permanecem disponíveis como sinais não confirmados.")
        elif specificity_status != "TARGET_SPECIFIC":
            caveats.append("A especificidade do grupo alvo não foi estabelecida para todos os candidatos.")
        if any(c["support"]["status"] != "SUPPORT_AVAILABLE" for c in candidates):
            caveats.append("Suporte por reads não foi medido para todos os candidatos; zero em métricas indisponíveis não representa uma medição.")
        if any(c["support"]["status"] == "SUPPORT_AVAILABLE" and c["support"]["unique_templates"] == 0 for c in candidates):
            caveats.append("Há candidato com suporte medido e zero templates independentes registrados.")
        if control_status not in {"CONTROL_BELOW_SAMPLE", "CONTROL_NOT_DETECTED", "CONTROL_NOT_APPLICABLE"}:
            caveats.append("Controles ausentes ou com ressalvas; a recuperação não constitui confirmação biológica.")
        caveats.append("A atribuição taxonômica é condicionada ao painel e aos hits reportados; preferência no painel não confirma espécie.")
        if any(r["status"] != "AVAILABLE" for r in aligned_references):
            caveats.append("Intervalos de referência ausentes: a união de bases alinhadas está incompleta ou não foi medida.")
    if analysis_outcome == "NO_EVIDENCE_RECOVERED":
        # A negative computational result is not a biological claim: it
        # reports what this analysis did not recover, not that the target is
        # absent from the sample (sensitivity is not measured/guaranteed).
        caveats.append(
            "Ausência de evidência recuperada não demonstra ausência do "
            "vírus na amostra; nenhuma sensibilidade analítica é aferida "
            "ou garantida por este resultado."
        )
    gates: list[dict] = []

    metrics = {
        "candidate_count": len(candidates),
        "available_candidate_count": len(candidates),
        "promotion_eligible_candidate_count": 0,
        "qualifying_loci": 0,
        "qualification_status": "NOT_EVALUATED",
        "total_nonredundant_reference_bp": sum(item["aligned_reference_bp"] for item in aligned_references),
        "reference_coverage_status": (
            "NOT_EVALUATED" if not aligned_references or all(r["status"] == "NOT_EVALUATED" for r in aligned_references)
            else "AVAILABLE" if all(r["status"] == "AVAILABLE" for r in aligned_references)
            else "PARTIAL"
        ),
        "unique_templates": max((item["unique_templates"] for item in matched_support), default=0),
        "distinct_starts": max((item["distinct_starts"] for item in matched_support), default=0),
        "proper_pair_templates": max((item["proper_pair_templates"] for item in matched_support), default=0),
        "breadth_1x": max((item["breadth_1x"] for item in matched_coverage), default=0.0),
        "breadth_3x": max((item["breadth_3x"] for item in matched_coverage), default=0.0),
        "median_depth_covered": max((item["median_depth_covered"] for item in matched_coverage), default=0.0),
        "max_window_depth_fraction": max((item["max_window_depth_fraction"] for item in matched_coverage), default=0.0),
        "multi_assembler_locus_count": as_int(
            assembly_concordance.get("multi_assembler_locus_count")
        ),
    }

    document = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "sample_id": sample,
        "run_id": resolved_run_id,
        "execution_status": "done",
        "analysis_outcome": analysis_outcome,
        "evidence_level": "DETECTED" if candidates else "NO_SIGNAL",
        "shadow_mode": shadow,
        "reported_conclusion": (
            analysis_outcome
            if historical_compatibility is not None
            else conclusion_for(active_policy, analysis_outcome)
        ),
        "candidates": candidates,
        "caveats": list(dict.fromkeys(caveats)),
        "promotion_gates": gates,
        "specificity": {"status": specificity_status},
        "coverage": {
            "status": coverage_status,
            "by_candidate": [
                item["coverage"] | {"candidate_id": item["candidate_id"]}
                for item in candidates
            ],
        },
        "controls": {"status": control_status, "metrics": {}},
        "provenance": provenance,
        "scientific_revision": SCIENCE_REVISION,
        "evidence_label": "Candidatos recuperados" if candidates else "Nenhum candidato recuperado",
        "reference_coverage": {
            "unit": "UNION_REFERENCE_POSITIONS_PER_REFERENCE_SEGMENT",
            "biological_origin_confirmed": False,
            "by_reference": aligned_references,
        },
        "library_mode": library_mode,
        "metrics": metrics,
        # Read-only compatibility aliases for the existing dashboard/API.
        "specificity_status": specificity_status,
        "coverage_status": coverage_status,
        "control_status": control_status,
    }
    if assembly_concordance:
        document["analysis_observations"] = {
            "assembly_concordance": {
                "status": "AVAILABLE",
                "evidence_authority": "ANALYSIS",
                "multi_assembler_locus_count": as_int(
                    assembly_concordance.get("multi_assembler_locus_count")
                ),
            }
        }
    if identity is not None:
        document.update(identity)
    return validate_document(
        document,
        policy=active_policy,
        compatibility_mode=historical_compatibility,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create evidence documents")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--loci", required=True)
    parser.add_argument("--competitive", required=True)
    parser.add_argument("--read-support")
    parser.add_argument("--coverage")
    parser.add_argument("--control-status", default="UNCONTROLLED")
    parser.add_argument("--library-mode", choices=["shotgun", "amplicon", "targeted", "unknown"], default="unknown")
    parser.add_argument("--out", required=True)
    parser.add_argument("--provenance")
    parser.add_argument("--run-id")
    policy_group = parser.add_mutually_exclusive_group()
    policy_group.add_argument("--activation-policy")
    policy_group.add_argument("--experimental-activation-policy")
    parser.add_argument("--profiles")
    parser.add_argument("--assembly-concordance")
    args = parser.parse_args()
    read_support = read_tsv(args.read_support) if args.read_support and Path(args.read_support).stat().st_size else []
    coverage = read_tsv(args.coverage) if args.coverage and Path(args.coverage).stat().st_size else []
    provenance = {}
    if args.provenance:
        with open(args.provenance, "r", encoding="utf-8", errors="strict") as handle:
            provenance = json.load(handle)
    if args.experimental_activation_policy:
        policy = load_experimental_activation_policy(
            args.experimental_activation_policy,
            profiles_path=args.profiles,
        )
    else:
        policy = load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)
    assembly_concordance = {}
    if args.assembly_concordance:
        with open(args.assembly_concordance, "r", encoding="utf-8", errors="strict") as handle:
            assembly_concordance = json.load(handle)
    result = classify(
        args.sample, read_tsv(args.loci), read_tsv(args.competitive), read_support, coverage,
        args.control_status, args.library_mode, policy["shadow_mode"],
        provenance, args.run_id, policy, assembly_concordance,
    )
    write_json_atomic(args.out, result)


if __name__ == "__main__":
    main()
