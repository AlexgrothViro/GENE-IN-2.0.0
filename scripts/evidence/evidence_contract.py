#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy

try:
    from .activation_policy import (
        POLICY_IDENTITY_FIELDS,
        conclusion_for,
        load_public_activation_policy,
        policy_identity,
        validate_policy_identity,
    )
    from .evidence_profile import validate_gate_results
except ImportError:
    from activation_policy import (
        POLICY_IDENTITY_FIELDS,
        conclusion_for,
        load_public_activation_policy,
        policy_identity,
        validate_policy_identity,
    )
    from evidence_profile import validate_gate_results


SCHEMA_VERSION = "2.0"
PIPELINE_VERSION = "2.0.0-alpha.2"
EVIDENCE_LEVELS = {"DETECTED", "REVIEW", "NO_SIGNAL", "NOT_EVALUABLE"}
ANALYSIS_OUTCOMES = {
    "EVIDENCE_RECOVERED", "CANDIDATES_FOR_REVIEW", "NO_EVIDENCE_RECOVERED", "NOT_EVALUABLE",
}
EXECUTION_STATUSES = {"queued", "running", "done", "warning", "blocked", "failed", "cancelled"}
# CONTROL_NOT_APPLICABLE marca a própria linha de controle. Não é um controle
# validado da amostra e não libera DETECTED nem ACTIONABLE.
CONTROL_PASS = {"CONTROL_BELOW_SAMPLE", "CONTROL_NOT_DETECTED"}
TERMINAL_EXECUTION_STATUSES = {"done", "warning", "blocked", "failed", "cancelled"}
FAILED_EXECUTION_STATUSES = {"blocked", "failed", "cancelled"}


def evidence_label(value: dict) -> str:
    """Public wording for the existing recovery codes, including old runs."""
    return {
        "EVIDENCE_RECOVERED": "Candidatos recuperados",
        "CANDIDATES_FOR_REVIEW": "Candidatos para revisão",
        "NO_EVIDENCE_RECOVERED": "Nenhum candidato recuperado",
        "NOT_EVALUABLE": "Não avaliável",
    }.get(value.get("analysis_outcome"), "Não avaliável")


# Rótulos exibidos ao usuário. Os códigos contratuais DETECTED e
# EVIDENCE_RECOVERED permanecem no JSON para compatibilidade.
PUBLIC_REVIEW_LABELS = {
    "EVIDENCE_RECOVERED": "CANDIDATOS_PARA_REVISAO",
    "CANDIDATES_FOR_REVIEW": "CANDIDATOS_PARA_REVISAO",
    "DETECTED": "CANDIDATOS_PARA_REVISAO",
    "REVIEW": "CANDIDATOS_PARA_REVISAO",
    "NO_EVIDENCE_RECOVERED": "SEM_CANDIDATOS_PARA_REVISAO",
    "NO_SIGNAL": "SEM_CANDIDATOS_PARA_REVISAO",
}


def labels_for_control(
    control_status: str,
    *,
    has_candidates: bool,
    only_short_builder: bool = False,
) -> tuple[str, str]:
    """Return ``(analysis_outcome, evidence_level)`` for one execution.

    A validated positive or negative control may carry ``DETECTED``. Without
    that state, candidates stay available for review and the execution label
    is ``REVIEW``. ``CONTROL_NOT_APPLICABLE`` is not a validated control.
    A sample whose only evidence is a Builder fragment shorter than 200 bp
    also stays at ``REVIEW``, including inside a batch.
    """
    if not has_candidates:
        return "NO_EVIDENCE_RECOVERED", "NO_SIGNAL"
    if only_short_builder or control_status not in CONTROL_PASS:
        return "CANDIDATES_FOR_REVIEW", "REVIEW"
    return "EVIDENCE_RECOVERED", "DETECTED"


def public_review_label(code: object) -> str:
    """Map a contract code to the neutral label shown in reports and the panel."""
    return PUBLIC_REVIEW_LABELS.get(str(code), str(code))


def _nonnegative_metric(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{context} must be finite and non-negative")
    return number


def _validate_public_state(execution_status: object, analysis_outcome: object,
                           evidence_level: object, *, context: str = "") -> None:
    prefix = f"{context} " if context else ""
    if execution_status not in EXECUTION_STATUSES:
        raise ValueError(f"invalid {prefix}execution_status")
    if execution_status not in TERMINAL_EXECUTION_STATUSES:
        raise ValueError(f"{prefix}evidence document requires a terminal execution_status")
    if analysis_outcome not in ANALYSIS_OUTCOMES:
        raise ValueError(f"invalid {prefix}analysis_outcome")
    if evidence_level not in EVIDENCE_LEVELS:
        raise ValueError(f"invalid {prefix}evidence_level")
    if execution_status in FAILED_EXECUTION_STATUSES and analysis_outcome != "NOT_EVALUABLE":
        raise ValueError(
            f"{prefix}failed, blocked, or cancelled execution requires NOT_EVALUABLE"
        )
    if analysis_outcome == "NOT_EVALUABLE" and evidence_level != "NOT_EVALUABLE":
        raise ValueError("NOT_EVALUABLE outcome requires NOT_EVALUABLE evidence level")
    if analysis_outcome != "NOT_EVALUABLE" and evidence_level == "NOT_EVALUABLE":
        raise ValueError("NOT_EVALUABLE evidence level requires NOT_EVALUABLE outcome")
    if analysis_outcome == "EVIDENCE_RECOVERED" and evidence_level != "DETECTED":
        raise ValueError("EVIDENCE_RECOVERED requires DETECTED evidence level")
    if analysis_outcome == "CANDIDATES_FOR_REVIEW" and evidence_level != "REVIEW":
        raise ValueError("CANDIDATES_FOR_REVIEW requires REVIEW evidence level")
    if evidence_level == "REVIEW" and analysis_outcome != "CANDIDATES_FOR_REVIEW":
        raise ValueError("REVIEW evidence level requires CANDIDATES_FOR_REVIEW outcome")
    if analysis_outcome == "NO_EVIDENCE_RECOVERED" and evidence_level != "NO_SIGNAL":
        raise ValueError("NO_EVIDENCE_RECOVERED requires NO_SIGNAL evidence level")


def _validate_compatibility_document(value: dict, compatibility_mode: str) -> None:
    if compatibility_mode == "historical_alpha2_fixture":
        if (
            value.get("run_id") != "fixture-alpha2-run"
            or value.get("sample_id") != "fixture-alpha2"
            or value.get("shadow_mode") is not True
            or value.get("provenance") != {"fixture": True}
        ):
            raise ValueError("historical Alpha.2 compatibility is restricted to the frozen fixture")
    elif compatibility_mode == "explicit_legacy_adaptation":
        adaptation = value.get("provenance", {}).get("legacy_adaptation", {})
        if adaptation.get("mode") != "EXPLICIT" or not adaptation.get("adaptation_id"):
            raise ValueError("legacy compatibility requires an explicit traceable adaptation")
    else:
        raise ValueError(f"unsupported evidence compatibility mode: {compatibility_mode}")
    present_identity = {field for field in POLICY_IDENTITY_FIELDS if field != "shadow_mode"} & set(value)
    if present_identity:
        raise ValueError("historical evidence cannot carry a partial active policy identity")


def validate_document(
    value: object,
    *,
    policy: dict | None = None,
    compatibility_mode: str | None = None,
) -> dict:
    if not isinstance(value, dict):
        raise ValueError("evidence document must be an object")
    required = {
        "schema_version", "pipeline_version", "sample_id", "run_id", "execution_status",
        "analysis_outcome", "evidence_level", "shadow_mode", "reported_conclusion",
        "candidates", "caveats", "promotion_gates", "specificity", "coverage", "controls",
        "provenance",
    }
    missing = required - set(value)
    if missing:
        raise ValueError("evidence document missing fields: " + ", ".join(sorted(missing)))
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported evidence schema: {value['schema_version']}")
    if value["pipeline_version"] != PIPELINE_VERSION:
        raise ValueError(f"unsupported evidence pipeline: {value['pipeline_version']}")
    for name in ("sample_id", "run_id"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise ValueError(f"{name} is required")
    _validate_public_state(
        value["execution_status"], value["analysis_outcome"], value["evidence_level"],
    )
    if not isinstance(value["shadow_mode"], bool):
        raise ValueError("shadow_mode must be boolean")
    if compatibility_mode is not None:
        _validate_compatibility_document(value, compatibility_mode)
        expected_conclusion = value["analysis_outcome"]
        active_policy = load_public_activation_policy()
    else:
        active_policy = policy or load_public_activation_policy()
        expected_identity = policy_identity(active_policy)
        validate_policy_identity(
            value, expected=expected_identity, context="evidence document",
        )
        expected_conclusion = conclusion_for(active_policy, value["analysis_outcome"])
    if value["reported_conclusion"] != expected_conclusion:
        raise ValueError(f"evidence conclusion must be {expected_conclusion}")
    for name in ("candidates", "caveats", "promotion_gates"):
        if not isinstance(value[name], list):
            raise ValueError(f"{name} must be a list")
    validate_gate_results(active_policy, value["promotion_gates"])
    for name in ("specificity", "coverage", "controls", "provenance"):
        if not isinstance(value[name], dict):
            raise ValueError(f"{name} must be an object")
    for name in ("specificity", "coverage", "controls"):
        if not isinstance(value[name].get("status"), str) or not value[name]["status"]:
            raise ValueError(f"{name}.status is required")
    if "by_candidate" not in value["coverage"] or not isinstance(value["coverage"]["by_candidate"], list):
        raise ValueError("coverage.by_candidate must be a list")
    for candidate in value["candidates"]:
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be an object")
        missing_candidate = {
            "candidate_id", "reference_id", "category", "locus_id", "query_ids",
            "orientation", "candidate_class", "promotion_status", "blocking_reasons",
        } - set(candidate)
        if missing_candidate:
            raise ValueError("candidate missing fields: " + ", ".join(sorted(missing_candidate)))
        for name in ("candidate_id", "reference_id", "category", "locus_id"):
            if not isinstance(candidate[name], str) or not candidate[name].strip():
                raise ValueError(f"candidate.{name} is required")
        if candidate["orientation"] not in {"+", "-", "UNKNOWN"}:
            raise ValueError("candidate.orientation must be +, -, or UNKNOWN")
        if not isinstance(candidate["query_ids"], list):
            raise ValueError("candidate.query_ids must be a list")
        if candidate["candidate_class"] not in {
            "EXPLORATORY_FRAGMENT", "LOCUS_CANDIDATE", "LEGACY_INCOMPATIBLE",
        }:
            raise ValueError("invalid candidate.candidate_class")
        if candidate["promotion_status"] != "AVAILABLE":
            raise ValueError("invalid candidate.promotion_status")
        if not isinstance(candidate["blocking_reasons"], list):
            raise ValueError("candidate.blocking_reasons must be a list")
        if candidate["blocking_reasons"]:
            raise ValueError("unrestricted candidates cannot contain blocking reasons")
        support = candidate.get("support")
        if isinstance(support, dict):
            for name in ("unique_templates", "distinct_starts", "proper_pair_templates"):
                metric = _nonnegative_metric(support.get(name), f"candidate.support.{name}")
                if support.get("status") != "SUPPORT_AVAILABLE" and metric != 0:
                    raise ValueError(
                        f"candidate.support.{name} must be zero when support is not measured"
                    )
        coverage = candidate.get("coverage")
        if isinstance(coverage, dict):
            for name in (
                "breadth_1x", "breadth_3x", "median_depth_covered",
                "max_window_depth_fraction",
            ):
                metric = _nonnegative_metric(coverage.get(name), f"candidate.coverage.{name}")
                if coverage.get("status") != "AVAILABLE" and metric != 0:
                    raise ValueError(
                        f"candidate.coverage.{name} must be zero when coverage is not measured"
                    )
    if value["analysis_outcome"] == "NO_EVIDENCE_RECOVERED" and value["candidates"]:
        raise ValueError("NO_EVIDENCE_RECOVERED requires an empty candidate list")
    if value["analysis_outcome"] == "EVIDENCE_RECOVERED" and not value["candidates"]:
        raise ValueError("EVIDENCE_RECOVERED requires at least one candidate")
    if value["analysis_outcome"] == "CANDIDATES_FOR_REVIEW" and not value["candidates"]:
        raise ValueError("CANDIDATES_FOR_REVIEW requires at least one candidate")
    if value["analysis_outcome"] != "NOT_EVALUABLE":
        metrics = value.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("evaluable evidence requires primary metrics")
        required_metrics = {
            "candidate_count", "promotion_eligible_candidate_count", "qualifying_loci",
            "total_nonredundant_reference_bp", "unique_templates", "distinct_starts",
            "proper_pair_templates", "breadth_1x", "breadth_3x",
            "median_depth_covered", "max_window_depth_fraction",
        }
        missing_metrics = required_metrics - set(metrics)
        if missing_metrics:
            raise ValueError(
                "primary metrics missing fields: " + ", ".join(sorted(missing_metrics))
            )
        for name in required_metrics:
            _nonnegative_metric(metrics[name], f"metrics.{name}")
        if metrics["candidate_count"] != len(value["candidates"]):
            raise ValueError("metrics.candidate_count does not match candidates")
    if "scientific_revision" in value:
        if value["scientific_revision"] != "scientific_review_20261005_v1":
            raise ValueError("unsupported scientific revision")
        if value.get("evidence_label") != evidence_label(value):
            raise ValueError("evidence_label does not match recovery outcome")
        if value["analysis_outcome"] != "NOT_EVALUABLE":
            if (
                metrics.get("available_candidate_count") != len(value["candidates"])
                or metrics["promotion_eligible_candidate_count"] != 0
                or metrics["qualifying_loci"] != 0
                or metrics.get("qualification_status") != "NOT_EVALUATED"
            ):
                raise ValueError("availability must not be reported as scientific qualification")
            for candidate in value["candidates"]:
                if candidate.get("availability_status") != "AVAILABLE_FOR_REVIEW" or candidate.get("qualification_status") != "NOT_EVALUATED":
                    raise ValueError("invalid candidate availability/qualification")
                if candidate.get("taxonomic_status") not in {"PANEL_TAXON_PREFERRED", "AMBIGUOUS", "NON_TARGET_BEST", "NOT_EVALUATED"}:
                    raise ValueError("invalid candidate taxonomic_status")
                if candidate.get("taxonomic_scope") != "REPORTED_LABELLED_PANEL_ONLY":
                    raise ValueError("invalid taxonomic scope")
            reference_coverage = value.get("reference_coverage", {})
            if reference_coverage.get("unit") != "UNION_REFERENCE_POSITIONS_PER_REFERENCE_SEGMENT" or reference_coverage.get("biological_origin_confirmed") is not False:
                raise ValueError("invalid reference coverage unit/origin")
            from collections import defaultdict
            try:
                from .common import interval_size, parse_intervals
            except ImportError:
                from common import interval_size, parse_intervals
            expected_intervals = defaultdict(list)
            for candidate in value["candidates"]:
                expected_intervals[(candidate["reference_id"], candidate["segment"])].extend(parse_intervals(candidate["reference_intervals"]))
            expected_bases = {key: interval_size(intervals) for key, intervals in expected_intervals.items()}
            actual = {}
            for row in reference_coverage.get("by_reference", []):
                key = (row["reference_id"], row["segment"])
                if key in actual:
                    raise ValueError("duplicate reference coverage key")
                positions = parse_intervals(row["reference_intervals"])
                if any(start < 1 or end < start or (row.get("reference_length") and end > row["reference_length"]) for start, end in positions):
                    raise ValueError("invalid reference coverage coordinates")
                actual[key] = interval_size(positions)
                if row["aligned_reference_bp"] != actual[key]:
                    raise ValueError("reference coverage count does not match intervals")
                if interval_size([*positions, *expected_intervals.get(key, [])]) != actual[key]:
                    raise ValueError("reference coverage union does not match candidates")
            if actual != expected_bases or sum(actual.values()) != metrics["total_nonredundant_reference_bp"]:
                raise ValueError("nonredundant reference bases do not match candidate union")
    return value


def adapt_legacy_document(value: dict, *, adaptation_id: str | None = None) -> dict:
    """Explicit, traceable migration helper; never used by public read paths."""
    if value.get("schema_version") == SCHEMA_VERSION and value.get("pipeline_version") == PIPELINE_VERSION:
        return validate_document(deepcopy(value))
    if not isinstance(adaptation_id, str) or not adaptation_id.strip():
        raise ValueError("legacy adaptation requires an explicit adaptation_id")
    source_sha256 = hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    sample_id = str(value.get("sample_id") or value.get("sample") or "UNKNOWN")
    old_level = str(value.get("evidence_level") or value.get("evidence_class") or "REVIEW")
    has_signal = old_level not in {"", "INCONCLUSIVE", "NO_VIRAL_HITS", "NONE"}
    candidates = []
    if has_signal:
        candidates.append({
            "candidate_id": "legacy-candidate",
            "reference_id": "LEGACY_UNKNOWN",
            "category": "UNLABELED",
            "locus_id": "LEGACY_UNSCOPED",
            "query_ids": [],
            "orientation": "UNKNOWN",
            "legacy_label": old_level,
            "candidate_class": "LEGACY_INCOMPATIBLE",
            "promotion_status": "AVAILABLE",
            "blocking_reasons": [],
            "specificity_status": str(value.get("specificity_status", "NOT_EVALUATED")),
        })
    active_policy = load_public_activation_policy()
    document = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "sample_id": sample_id,
        "run_id": str(value.get("run_id") or f"legacy-{sample_id}"),
        "execution_status": "done",
        "analysis_outcome": "NOT_EVALUABLE",
        "evidence_level": "NOT_EVALUABLE",
        "shadow_mode": False,
        "reported_conclusion": "NOT_EVALUABLE",
        "candidates": candidates,
        "caveats": [
            "Resultado legado adaptado explicitamente para auditoria; nenhum nível E1 é atribuído automaticamente.",
            "Limiares científicos permanecem em calibração.",
        ],
        "promotion_gates": [],
        "specificity": {"status": str(value.get("specificity_status", "NOT_EVALUATED"))},
        "coverage": {"status": str(value.get("coverage_status", "NOT_EVALUATED")), "by_candidate": []},
        "controls": {"status": str(value.get("control_status", "UNCONTROLLED")), "metrics": {}},
        "provenance": {
            **deepcopy(value.get("provenance") or {}),
            "legacy_adaptation": {
                "mode": "EXPLICIT",
                "adaptation_id": adaptation_id.strip(),
                "source_sha256": source_sha256,
                "source_schema_version": value.get("schema_version"),
            },
        },
        "legacy": deepcopy(value),
    }
    return validate_document(document, compatibility_mode="explicit_legacy_adaptation")


def promote_for_public_output(
    value: object,
    *,
    policy: dict | None = None,
    expected_identity: dict | None = None,
    compatibility_mode: str | None = None,
) -> dict:
    """Validate the public evidence representation without adapting legacy input."""
    if not isinstance(value, dict):
        raise ValueError("evidence output must be an object")
    if isinstance(value.get("samples"), list):
        required = {
            "schema_version", "pipeline_version", "run_id", "batch_id",
            "shadow_mode", "reported_conclusion", "samples",
        }
        missing = required - set(value)
        if missing:
            raise ValueError("batch evidence missing fields: " + ", ".join(sorted(missing)))
        if value["schema_version"] != SCHEMA_VERSION or value["pipeline_version"] != PIPELINE_VERSION:
            raise ValueError("batch evidence contract version is incompatible")
        if not isinstance(value["shadow_mode"], bool):
            raise ValueError("batch shadow_mode must be boolean")
        active_policy = policy or load_public_activation_policy()
        active_identity = policy_identity(active_policy)
        if expected_identity is not None:
            validate_policy_identity(active_identity, expected=expected_identity, context="active batch policy")
        batch_identity = validate_policy_identity(
            value, expected=active_identity, context="batch evidence",
        )
        expected_batch_conclusion = conclusion_for(active_policy, "EVIDENCE_RECOVERED")
        if value["reported_conclusion"] != expected_batch_conclusion:
            raise ValueError(f"batch reported_conclusion must be {expected_batch_conclusion}")
        if not isinstance(value["run_id"], str) or not value["run_id"].strip():
            raise ValueError("batch run_id is required")
        if not isinstance(value["batch_id"], str) or not value["batch_id"].strip():
            raise ValueError("batch batch_id is required")
        output = deepcopy(value)
        seen_samples: set[str] = set()
        seen_child_runs: set[str] = set()
        for sample in output["samples"]:
            if not isinstance(sample, dict):
                raise ValueError("batch sample must be an object")
            required_sample = {
                "sample_id", "child_run_id", "execution_status", "analysis_outcome", "evidence_level",
                "reported_conclusion", "caveats", "promotion_gates",
            }
            if required_sample - set(sample):
                raise ValueError("batch sample missing public evidence fields")
            if not isinstance(sample["sample_id"], str) or not sample["sample_id"].strip():
                raise ValueError("batch sample sample_id is required")
            if not isinstance(sample["child_run_id"], str) or not sample["child_run_id"].strip():
                raise ValueError("batch sample child_run_id is required")
            if sample["sample_id"] in seen_samples:
                raise ValueError("batch sample_id must be unique")
            if sample["child_run_id"] in seen_child_runs:
                raise ValueError("batch child_run_id must be unique")
            seen_samples.add(sample["sample_id"])
            seen_child_runs.add(sample["child_run_id"])
            validate_policy_identity(
                sample, expected=batch_identity, context="batch sample",
            )
            expected_sample_conclusion = conclusion_for(active_policy, sample["analysis_outcome"])
            if sample["reported_conclusion"] != expected_sample_conclusion:
                raise ValueError("batch sample reported_conclusion conflicts with policy")
            _validate_public_state(
                sample["execution_status"], sample["analysis_outcome"],
                sample["evidence_level"], context="batch sample",
            )
            validate_gate_results(active_policy, sample["promotion_gates"])
        return output
    return validate_document(
        deepcopy(value), policy=policy, compatibility_mode=compatibility_mode,
    )


def not_evaluable_document(
    sample_id: str,
    run_id: str,
    reason: str,
    provenance: dict | None = None,
    policy: dict | None = None,
    identity: dict | None = None,
) -> dict:
    if policy is not None and identity is not None:
        raise ValueError("provide policy or identity, not both")
    active_policy = policy or load_public_activation_policy()
    resolved_identity = policy_identity(active_policy)
    if identity is not None:
        validate_policy_identity(identity, expected=resolved_identity, context="failure evidence policy identity")
    document = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "sample_id": sample_id,
        "run_id": run_id,
        "execution_status": "failed",
        "analysis_outcome": "NOT_EVALUABLE",
        "evidence_level": "NOT_EVALUABLE",
        "shadow_mode": active_policy["shadow_mode"],
        "reported_conclusion": conclusion_for(active_policy, "NOT_EVALUABLE"),
        "candidates": [],
        "caveats": [reason],
        "promotion_gates": [],
        "specificity": {"status": "NOT_EVALUATED"},
        "coverage": {"status": "NOT_EVALUATED", "by_candidate": []},
        "controls": {"status": "NOT_EVALUATED", "metrics": {}},
        "provenance": provenance or {},
        **resolved_identity,
    }
    return validate_document(document, policy=active_policy)
